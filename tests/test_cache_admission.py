"""Missing-field and high-cache admission evidence; synthetic, not sandbox acceptance."""
import copy
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_core as core
import memory_guard as guard
import runtime_memory as runtime
import cv_probe
import batch_acquisition
import test_cv
import test_acquisition
M=1048576
SOURCE={'path':'/proc/meminfo','fstype':'proc','mountRoot':'/','mountPoint':'/proc'}
MOUNTS='10 9 0:33 / /cg ro - cgroup cgroup rw,memory\n11 9 0:34 / /proc ro - proc proc rw'

def upper(dirty=4*M,writeback=2*M):
    raw=f'Dirty: {dirty//1024} kB\nWriteback: {writeback//1024} kB\nShmem: 999999 kB\n'
    return {'status':'available','source':SOURCE.copy(),'before':raw,'after':raw,'upperBoundsBytes':{'Dirty':dirty,'Writeback':writeback}}

def logged_baseline(second=False):
    # First file-LRU/cache values were nearby samples; second tuple was one sample.
    used,cache,inactive,rss=(1037201408,895987712,399163392,140689408) if second else (932937728,791973888,304316416,126312448)
    return {'status':'available','version':1,'memory.usage_in_bytes':str(used),'memory.limit_in_bytes':str(1073741824),
            'memory.failcnt':'7369317','memory.stat':f'total_cache {cache}\ntotal_inactive_file {inactive}\ntotal_rss {rss}',
            'memory.oom_control':'oom_kill_disable 0\nunder_oom 0','nativeProcMeminfo':upper()}

class CacheAdmissionTests(unittest.TestCase):
    def setUp(self):self.config=cv_probe.config_value()
    def evaluate(self,s,**kwargs):return guard.evaluate_guard(s,self.config,baseline=kwargs.pop('baseline',s),tree_rss=kwargs.pop('tree_rss',31113216),**kwargs)
    def test_log_based_synthetic_bounds_and_pressure_allow_stage_without_faking_raw_headroom(self):
        for second in (False,True):
            with self.subTest(second=second):
                s=logged_baseline(second);g=self.evaluate(s,reserve_mib=128)
                self.assertFalse(g['abort'],g);self.assertEqual(g['missingReclaimDeductionFields'],['total_shmem','total_dirty','total_writeback'])
                self.assertEqual(g['shmemDeduction'],'not_required_native_v1_file_lru')
                self.assertEqual(g['reclaimDeductionSources']['total_dirty'],'native_proc_global_upper_bound')
                self.assertLess(g['headroomToSkillRawCeilingBytes'],128*M);self.assertGreater(g['headroomForStageBytes'],128*M)
                self.assertEqual(g['cacheBackedAdmission']['used'],second);self.assertEqual(g['pressureStatus'],'unknown')
                unsupported=copy.deepcopy(s);unsupported.pop('nativeProcMeminfo');denied=self.evaluate(unsupported,reserve_mib=128)
                self.assertTrue(denied['abort']);self.assertEqual(denied['guardBasis'],'raw_usage_fallback')
    def test_stage_reserve_respects_soft_stop_boundary_and_process_budget(self):
        base=logged_baseline(True);base['nativeProcMeminfo']=upper(0,0)
        limit=int(base['memory.limit_in_bytes']);used=int(base['memory.usage_in_bytes'])
        for reserve in (32,64,128):
            working=int(limit*.8)-reserve*M
            for offset,blocked in ((0,False),(1,True)):
                s=copy.deepcopy(base);s['memory.stat']=f'total_cache {used}\ntotal_inactive_file {used-working-offset}'
                g=self.evaluate(s,reserve_mib=reserve)
                self.assertEqual(g['abort'],blocked,g)
                self.assertEqual(g['headroomForStageBytes'],reserve*M-offset)
        s=copy.deepcopy(base);g=self.evaluate(s,reserve_mib=128,tree_rss=129*M)
        self.assertTrue(g['abort']);self.assertIn('insufficient_process_stage_headroom',g['cacheBackedAdmission']['reasons'])

    def test_high_raw_requires_current_oom_failcnt_and_tree_evidence(self):
        base=logged_baseline(True)
        cases=[]
        for field,value in [('memory.oom_control',None),('memory.oom_control','under_oom 1'),('memory.failcnt',None),('memory.failcnt','-1')]:
            s=copy.deepcopy(base);s[field]=value;cases.append((field+str(value),s,base,31113216))
        s=copy.deepcopy(base);s['memory.failcnt']=str(int(base['memory.failcnt'])+1);cases.append(('new_failcnt',s,base,31113216))
        for name,baseline,tree in [('no_baseline',None,31113216),('wrong_version',{**base,'version':2},31113216),('unknown_tree',base,None),('full_tree',base,240*M)]:cases.append((name,base,baseline,tree))
        self.assertTrue(self.evaluate(base,tree_rss=256*M,reserve_mib=0)['abort'])
        s=copy.deepcopy(base);s['memory.usage_in_bytes']=s['memory.limit_in_bytes'];cases.append(('at_limit',s,s,31113216))
        for name,s,baseline,tree in cases:
            with self.subTest(name=name):self.assertTrue(self.evaluate(s,baseline=baseline,tree_rss=tree,reserve_mib=128)['abort'])
    def test_dirty_upper_bound_or_short_psi_spike_blocks_high_raw(self):
        base=logged_baseline(True);s=copy.deepcopy(base);s['nativeProcMeminfo']=upper(dirty=500*M)
        g=self.evaluate(s);self.assertTrue(g['abort']);self.assertEqual(g['inactiveFileCreditBytes'],0)
        for pressure in ('full avg10=1.10 avg60=0.00 total=100','full avg10=0.00 avg60=0.00 total=101'):
            s=copy.deepcopy(base);s['memory.pressure']=pressure;prior={**base,'memory.pressure':'full avg10=0.00 total=100'}
            g=self.evaluate(s,baseline=prior);self.assertTrue(g['abort']);self.assertEqual(g['reason'],'shared_cgroup_pressure')
        # Low raw keeps the original avg10 policy, even if its total changed.
        s=copy.deepcopy(base);s['memory.usage_in_bytes']=str(700*M);s['memory.pressure']='full avg10=0.00 total=101'
        self.assertFalse(self.evaluate(s,baseline={**s,'memory.pressure':'full avg10=0.00 total=100'})['abort'])
    def test_v1_missing_shmem_is_not_zero_and_known_same_scope_dirty_wins(self):
        s=logged_baseline();s.pop('nativeProcMeminfo');s['memory.stat']+='\ntotal_dirty 0\ntotal_writeback 0'
        g=self.evaluate(s);self.assertFalse(g['abort']);self.assertEqual(g['missingReclaimDeductionFields'],['total_shmem'])
        self.assertNotIn('total_shmem',g['reclaimDeductionBytes'])
        s['nativeProcMeminfo']=upper(dirty=500*M);g=self.evaluate(s)
        self.assertEqual(g['reclaimDeductionSources']['total_dirty'],'memory.stat_same_scope')
    def test_malformed_total_scope_never_falls_back_to_local_or_zero(self):
        for invalid in ('total_inactive_file -1','total_inactive_file 3\ntotal_inactive_file 4','total_cache nope'):
            s=logged_baseline();s['memory.stat']=invalid+'\ninactive_file 300000000\ncache 900000000\ndirty 0\nwriteback 0'
            g=self.evaluate(s);self.assertTrue(g['abort']);self.assertEqual(g['inactiveFileCreditBytes'],0)
        for invalid in ('total_dirty -1','total_dirty 0\ntotal_dirty 1'):
            s=logged_baseline();s.pop('nativeProcMeminfo');s['memory.stat']+='\n'+invalid+'\ntotal_writeback 0'
            self.assertEqual(self.evaluate(s)['inactiveFileCreditBytes'],0)
    def test_native_meminfo_strict_parser_and_untrusted_evidence(self):
        for raw in ('Dirty: 1 MB\nWriteback: 0 kB','Dirty: -1 kB\nWriteback: 0 kB','Dirty: 0 kB\nDirty: 1 kB\nWriteback: 0 kB','Dirty: 0 kB','Dirty: x kB\nWriteback: 0 kB'):
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):guard.parse_native_meminfo(raw)
        for change in ('fstype','units','bounds','missing'):
            s=logged_baseline(True)
            if change=='fstype':s['nativeProcMeminfo']['source']['fstype']='fuse.lxcfs'
            elif change=='units':s['nativeProcMeminfo']['before']='Dirty: 1 MB\nWriteback: 0 kB'
            elif change=='bounds':s['nativeProcMeminfo']['upperBoundsBytes']['Dirty']=0
            else:s['nativeProcMeminfo']['after']='Dirty: 0 kB'
            g=self.evaluate(s);self.assertTrue(g['abort']);self.assertEqual(g['guardBasis'],'raw_usage_fallback')
    def test_native_proc_mount_requires_longest_native_uncovered_source(self):
        self.assertEqual(core.native_proc_meminfo_source(MOUNTS.splitlines()),SOURCE)
        cases=[MOUNTS+'\n12 11 0:35 /meminfo /proc/meminfo ro - fuse.lxcfs lxcfs rw',MOUNTS+'\n12 11 0:35 / /proc/meminfo ro - proc proc rw',MOUNTS.replace(' / /proc ro - proc',' /other /proc ro - proc'),MOUNTS+'\n13 11 0:34 / /proc ro - proc proc rw']
        for mounts in cases:
            with self.assertRaises(core.ProbeError):core.native_proc_meminfo_source(mounts.splitlines())
        with patch.object(Path,'is_symlink',return_value=True):
            with self.assertRaises(core.ProbeError):core.native_proc_meminfo_source(MOUNTS.splitlines())
    def test_snapshot_brackets_cgroup_read_with_native_meminfo_and_records_permission_failure(self):
        s=logged_baseline();reads=[]
        def text(path,*args,**kwargs):
            path=str(path);reads.append(path)
            if path=='/proc/self/cgroup':return '2:memory:/sandbox'
            if path=='/proc/self/mountinfo':return MOUNTS
            if path.startswith('/cg/sandbox/'):return s.get(path.rsplit('/',1)[1]) or ''
            raise FileNotFoundError(path)
        with patch.object(Path,'read_text',new=text),patch.object(core,'native_proc_meminfo_read',side_effect=['Dirty: 1 kB\nWriteback: 4 kB','Dirty: 8 kB\nWriteback: 2 kB']):
            observed=core.cgroup_snapshot()
        self.assertEqual(observed['nativeProcMeminfo']['upperBoundsBytes'],{'Dirty':8192,'Writeback':4096})
        with patch.object(Path,'read_text',new=text),patch.object(core,'native_proc_meminfo_read',side_effect=PermissionError(13,'denied')):
            observed=core.cgroup_snapshot()
        self.assertEqual(observed['status'],'available');self.assertEqual(observed['nativeProcMeminfo']['status'],'unavailable')
    def test_resources_fixed_baseline_matches_monitor_and_detects_increment(self):
        import tempfile
        base=logged_baseline(True)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);core.write(root/'status.json',{'stage':'selection'})
            current=copy.deepcopy(base);current['memory.failcnt']=str(int(base['memory.failcnt'])+1)
            with patch.object(core,'cgroup_snapshot',side_effect=[base,base,current]),patch.object(guard,'process_tree_rss',return_value=31113216):
                resources=core.Resources(root);first=resources.sample();second=resources.sample()
            self.assertFalse(first['memoryEstimate']['abort']);self.assertEqual(second['memoryEstimate']['reason'],'shared_cgroup_limit_event')

    def test_monitor_and_resources_share_baseline_and_limit_event_decision(self):
        import tempfile
        base=logged_baseline(True);current=copy.deepcopy(base)
        current['memory.failcnt']=str(int(base['memory.failcnt'])+1)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);core.write(root/'status.json',{'stage':'selection'})
            with patch.object(core,'cgroup_snapshot',side_effect=[base,current]) as sampled,patch.object(guard,'process_tree_rss',return_value=31113216):
                monitor=runtime.StageMonitor(root,'selection')
                self.assertIs(monitor.sampler.baseline,monitor.baseline)
                monitor.observe()
            self.assertEqual(sampled.call_count,2)
            row=__import__('json').loads((root/'resources.ndjson').read_text().splitlines()[-1])
            self.assertEqual(row['memoryEstimate']['reason'],'shared_cgroup_limit_event')
            self.assertEqual(core.read(root/'memory-guard.json')['reason'],row['memoryEstimate']['reason'])
            with self.assertRaises(core.ProbeError):monitor.check()

class CacheAdmissionFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):test_cv.CvTests.setUpClass()
    @classmethod
    def tearDownClass(cls):test_cv.CvTests.tearDownClass()
    def test_two_logged_baselines_with_synthetic_new_evidence_reach_selection_details_and_full_cv(self):
        for second in (False,True):
            helper=test_cv.CvTests(methodName='runTest');helper.setUp()
            try:
                state=helper.helper.state;state['materialCount']=1;s=logged_baseline(second);output=helper.root.parent/('cache-flow-'+str(second))
                with patch.object(core,'cgroup_snapshot',return_value=s),patch.object(cv_probe,'cgroup_snapshot',return_value=s),patch.object(guard,'process_tree_rss',return_value=31113216),patch.object(runtime,'process_tree_rss',return_value=31113216),patch.object(cv_probe,'process_tree_rss',return_value=31113216):
                    result=batch_acquisition.run_batch(test_acquisition.request(),output)
                self.assertEqual(result['status'],'succeeded',result);self.assertEqual(state['selectionCalls'],1)
                self.assertEqual(len(state['detailIds']),1);self.assertEqual(state['videoGets'],1);self.assertEqual(result['completedCount'],1)
                self.assertEqual(list(output.rglob('*.html')),[output/'index.html'])
                self.assertFalse(core.read(output/'memory-guard.json')['abort'])
                self.assertEqual(core.read(output/'memory-guard.json')['cacheBackedAdmission']['used'],second)
            finally:helper.tearDown()
