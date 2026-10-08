import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_core as core
from batch_status import batch_status

class BatchStatusTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)/'batch'
        self.batch={'schemaVersion':1,'platform':'yuntu','packageVersion':'0.5.1','batchId':'fixture',
                    'status':'succeeded','stage':'complete','acquisition':'one_selection_all_A_then_serial_B',
                    'requestedCount':3,'selectedCount':3,'acquiredCount':3,'completedCount':3,'entries':[]}
    def tearDown(self):self.temp.cleanup()
    def entry(self,index,cv='succeeded',shots=2,root=None,attempt=None):
        run=root or self.root/'runs'/f'item-{index}';attempt=attempt or f'fixture-{index}'
        queued='succeeded' if cv=='succeeded' else 'running' if cv=='running' else 'failed' if cv=='failed' else 'pending'
        entry={'index':index,'materialId':str(index),'runDir':str(run),'attemptId':attempt,'status':queued,'acquisitionStatus':'video_ready','cvStatus':cv}
        core.write(run/'status.json',{'status':'video_ready','stage':'acquisition'})
        if cv!='pending':
            core.write(run/'cv'/attempt/'status.json',{'status':cv,'stage':'cv_complete' if cv!='running' else 'cv_decode_detect','pid':os.getpid()})
            if cv!='running':
                core.write(run/'cv'/attempt/'receipt.json',{'status':cv,'workerExitCode':0 if cv=='succeeded' else 1,
                    'errorCode':None if cv=='succeeded' else 'decode_failed','processCleanup':{'status':'completed'}})
                core.write(run/'cv'/attempt/'shots.json',{'shots':[{}]*shots})
        self.batch['entries'].append(entry)
        return entry
    def save(self):core.write(self.root/'batch.json',self.batch)
    def query_cli(self):
        return subprocess.run([sys.executable,'-B',str(core.ROOT/'scripts/run.py'),'status','--run-dir',str(self.root)],capture_output=True,text=True)
    def test_six_complete_113_shots_cli_and_read_only(self):
        self.batch.update(requestedCount=6,selectedCount=6,acquiredCount=6,completedCount=6)
        for i,shots in enumerate((2,18,28,13,50,2),1):self.entry(i,shots=shots)
        self.save();before={str(p):p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        with patch.object(core.Gateway,'post',side_effect=AssertionError('status must be local')):
            result=batch_status(self.root)
        self.assertEqual(result['cv']['status'],'succeeded');self.assertEqual(result['cv']['shotCount'],113)
        self.assertEqual(result['cv']['completedCount'],6);self.assertEqual(result['acquiredCount'],6)
        self.assertEqual(before,{str(p):p.read_bytes() for p in self.root.rglob('*') if p.is_file()})
        proc=self.query_cli();self.assertEqual(proc.returncode,0,proc.stderr)
        self.assertEqual(json.loads(proc.stdout)['cv']['status'],'succeeded')
    def test_acquisition_failed_and_pending_cv_stays_not_run(self):
        self.batch.update(status='failed',stage='acquisition',completedCount=0,acquiredCount=0,errorCode='media_input_limit')
        for i in range(1,4):
            e=self.entry(i,cv='pending');e.pop('attemptId')
            e['acquisitionStatus']='failed' if i==1 else 'pending';e['status']='failed' if i==1 else 'pending'
            core.write(Path(e['runDir'])/'status.json',{'status':e['acquisitionStatus']})
        self.save();result=batch_status(self.root)
        self.assertEqual(result['status'],'failed');self.assertEqual(result['cv']['status'],'not_run')
        self.assertEqual(result['cv']['pendingCount'],3);self.assertEqual(self.query_cli().returncode,1)
    def test_running_with_completed_and_pending_entries(self):
        self.batch.update(status='running',stage='cv',completedCount=1)
        self.entry(1);self.entry(2,cv='running');self.entry(3,cv='pending');self.save()
        result=batch_status(self.root)
        self.assertEqual(result['status'],'running');self.assertEqual(result['cv']['status'],'running')
        self.assertEqual((result['cv']['completedCount'],result['cv']['runningCount'],result['cv']['pendingCount']),(1,1,1))
    def test_interrupted_worker_is_reported_without_recovery(self):
        self.batch.update(status='running',stage='cv',completedCount=0)
        self.entry(1,cv='running');self.entry(2,cv='pending');self.entry(3,cv='pending');self.save()
        with patch('batch_status.recorded_process_alive',return_value=False):result=batch_status(self.root)
        self.assertEqual(result['status'],'interrupted');self.assertEqual(result['cv']['interruptedCount'],1)
        self.assertEqual(result['nextAction'],'inspect_saved_state_no_automatic_retry')
    def test_cv_failure_keeps_success_and_pending_counts(self):
        self.batch.update(status='failed',stage='cv',completedCount=1,errorCode='decode_failed')
        self.entry(1);self.entry(2,cv='failed');self.entry(3,cv='pending');self.save()
        result=batch_status(self.root)
        self.assertEqual(result['cv']['status'],'failed');self.assertEqual(result['cv']['failedCount'],1)
        self.assertEqual(result['cv']['completedCount'],1);self.assertEqual(result['cv']['pendingCount'],1)
    def test_shortage_is_partial_batch_but_selected_cv_succeeded(self):
        self.batch.update(status='partial',selectedCount=1,acquiredCount=1,completedCount=1,shortageCount=2)
        self.entry(1);self.save();result=batch_status(self.root)
        self.assertEqual(result['status'],'partial');self.assertEqual(result['cv']['status'],'succeeded')
        self.assertEqual(result['shortageCount'],2)
    def test_delivery_failure_does_not_erase_successful_cv(self):
        self.batch.update(status='failed',stage='delivery',errorCode='working_set_ceiling')
        for i in range(1,4):self.entry(i)
        self.save();result=batch_status(self.root)
        self.assertEqual(result['status'],'failed');self.assertEqual(result['cv']['status'],'succeeded')
        self.assertEqual(result['cv']['completedCount'],3)
    def test_repeated_existing_a_binds_each_attempt_not_latest(self):
        run=Path(self.temp.name)/'input';self.batch.update(acquisition='reused_A_only',selectedCount=2,requestedCount=2,completedCount=2)
        self.entry(1,root=run,attempt='first',shots=2);self.entry(2,root=run,attempt='second',shots=18)
        core.write(run/'cv/latest.json',{'attemptId':'unrelated'})
        self.save();result=batch_status(self.root)
        self.assertEqual(result['cv']['completedCount'],2);self.assertEqual(result['cv']['shotCount'],20)
        self.assertEqual([e['attemptId'] for e in result['entries']],['first','second'])
    def test_missing_receipt_does_not_claim_success(self):
        for i in range(1,4):self.entry(i)
        attempt=self.root/'runs/item-2/cv/fixture-2'
        (attempt/'receipt.json').unlink();core.write(attempt/'status.json',{'status':'succeeded'})
        self.save();result=batch_status(self.root)
        self.assertEqual(result['status'],'unconfirmed');self.assertEqual(result['cv']['completedCount'],2)
        self.assertEqual(result['cv']['unconfirmedCount'],1);self.assertEqual(self.query_cli().returncode,1)
    def test_unconfirmed_cleanup_is_not_success(self):
        for i in range(1,4):self.entry(i)
        path=self.root/'runs/item-1/cv/fixture-1/receipt.json'
        receipt=core.read(path);receipt['processCleanup']['status']='unconfirmed';core.write(path,receipt)
        self.save();result=batch_status(self.root)
        self.assertEqual(result['cv']['status'],'failed');self.assertEqual(result['cv']['completedCount'],2)
    def test_single_run_status_keeps_original_contract(self):
        core.write(self.root/'status.json',{'status':'video_ready','stage':'acquisition'})
        proc=self.query_cli();self.assertEqual(proc.returncode,0,proc.stderr)
        result=json.loads(proc.stdout);self.assertNotIn('mode',result)
        self.assertEqual(result['cv']['status'],'not_run');self.assertEqual(result['nextAction'],'probe-cv')
    def test_normal_batch_rejects_escaped_run_directory(self):
        self.entry(1,root=Path(self.temp.name)/'outside');self.entry(2);self.entry(3);self.save()
        with self.assertRaises(core.ProbeError) as error:batch_status(self.root)
        self.assertEqual(error.exception.code,'batch_output_overlap')

    def test_dead_batch_during_acquisition_is_interrupted_without_cv(self):
        self.batch.update(status='running',stage='acquisition',pid=99999999,completedCount=0)
        self.batch['entries']=[{'index':i,'status':'pending','acquisitionStatus':'pending','cvStatus':'pending'} for i in range(1,4)]
        self.save()
        with patch('batch_status.recorded_process_alive',return_value=False):result=batch_status(self.root)
        self.assertEqual(result['status'],'interrupted');self.assertEqual(result['cv']['status'],'not_run')

    def test_supervisor_finalizing_receipt_is_still_running(self):
        self.batch.update(status='running',stage='cv',completedCount=0)
        self.entry(1,cv='running');self.entry(2,cv='pending');self.entry(3,cv='pending')
        core.write(self.root/'runs/item-1/cv/fixture-1/status.json',{'status':'succeeded','pid':os.getpid()})
        self.save();result=batch_status(self.root)
        self.assertEqual(result['cv']['status'],'running');self.assertEqual(result['cv']['completedCount'],0)

    def test_failure_before_worker_start_is_reported_from_bound_entry(self):
        self.batch.update(status='failed',stage='cv',completedCount=0,errorCode='artifact_changed')
        e=self.entry(1,cv='pending');e.update(status='failed',cvStatus='failed',errorCode='artifact_changed')
        self.entry(2,cv='pending');self.entry(3,cv='pending');self.save()
        result=batch_status(self.root)
        self.assertEqual(result['cv']['status'],'failed');self.assertEqual(result['cv']['failedCount'],1)
