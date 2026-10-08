"""Read-only batch observations, bound to each queued CV attempt."""
from pathlib import Path
import re
from probe_core import ROOT, ProbeError, read, safe_file, external_root
from cv_probe import recorded_process_alive


def metadata(root,relative):
    path=Path(root)/relative
    if not path.exists():return None
    path=safe_file(root,relative)
    if path.stat().st_size>4*1024*1024:raise ProbeError('batch_status_metadata_limit')
    value=read(path)
    if not isinstance(value,dict):raise ProbeError('batch_status_metadata_invalid')
    return value


def attempt_status(run,attempt_id,queued):
    if not attempt_id:
        return {'status':'running' if queued.get('cvStatus')=='running' else 'pending',
                'attemptId':None,'stage':'cv_preparing' if queued.get('cvStatus')=='running' else None}
    if not isinstance(attempt_id,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}',attempt_id):raise ProbeError('cv_attempt_id_invalid')
    state=metadata(run,f'cv/{attempt_id}/status.json') or {}
    receipt=metadata(run,f'cv/{attempt_id}/receipt.json')
    observed=state.get('status')
    error=state.get('errorCode')
    if receipt:
        observed=receipt.get('status');error=receipt.get('errorCode')
        if observed=='succeeded' and (receipt.get('workerExitCode')!=0 or receipt.get('processCleanup',{}).get('status')!='completed'):
            observed='failed';error='process_cleanup_unconfirmed' if receipt.get('processCleanup',{}).get('status')!='completed' else 'cv_worker_failed'
    elif observed=='running':
        process=metadata(run,f'cv/{attempt_id}/process.json') or {}
        if not recorded_process_alive({**state,**process}) and not recorded_process_alive({'pid':state.get('pid')}):
            observed='interrupted';error='previous_execution_interrupted'
    elif observed=='succeeded':
        observed='running' if recorded_process_alive({'pid':state.get('pid')}) else 'unconfirmed'
        error=None if observed=='running' else 'cv_receipt_missing'
    elif not observed:
        observed='pending' if queued['status']=='pending' else 'running' if queued['status']=='running' else 'failed' if queued['status']=='failed' else 'unconfirmed'
        error=queued.get('errorCode') if observed=='failed' else 'cv_state_missing' if observed=='unconfirmed' else None
    if observed not in ('pending','running','succeeded','failed','interrupted','unconfirmed'):
        observed='unconfirmed';error='cv_state_invalid'
    shots=metadata(run,f'cv/{attempt_id}/shots.json') if observed=='succeeded' else None
    shot_count=len(shots['shots']) if shots and isinstance(shots.get('shots'),list) else None
    return {'status':observed,'attemptId':attempt_id,'stage':state.get('stage'),
            'errorCode':error,'failureStage':state.get('failureStage'),'shotCount':shot_count,
            'workerExitCode':receipt.get('workerExitCode') if receipt else None,
            'processCleanup':receipt.get('processCleanup') if receipt else None,
            'statusSource':'receipt' if receipt else 'attempt_status' if state else 'batch_entry'}


def batch_status(root):
    root=Path(root);batch=metadata(root,'batch.json')
    if not batch or batch.get('schemaVersion')!=1 or batch.get('platform')!=read(ROOT/'config/platform.json')['platform']:raise ProbeError('batch_status_invalid')
    entries=batch.get('entries')
    if not isinstance(entries,list) or len(entries)>10:raise ProbeError('batch_status_invalid')
    observed=[];counts={key:0 for key in ('pending','running','succeeded','failed','interrupted','unconfirmed')}
    for entry in entries:
        if not isinstance(entry,dict) or entry.get('status') not in ('pending','running','succeeded','failed'):raise ProbeError('batch_status_invalid')
        run=entry.get('runDir')
        if run:
            if not isinstance(run,str) or not Path(run).is_absolute():raise ProbeError('batch_status_invalid')
            run=external_root(run)
            if batch.get('acquisition')!='reused_A_only' and not run.is_relative_to(root.resolve()):raise ProbeError('batch_output_overlap')
            acquisition=metadata(run,'status.json') or {}
            cv=attempt_status(run,entry.get('attemptId'),entry)
        else:acquisition={};cv={'status':'pending','attemptId':None}
        counts[cv['status']]+=1
        observed.append({'index':entry.get('index'),'materialId':entry.get('materialId'),
                         'status':entry['status'],'acquisitionStatus':acquisition.get('status') or entry.get('acquisitionStatus','pending'),
                         'cvStatus':cv['status'],'attemptId':cv['attemptId'],'cv':cv,
                         'errorCode':cv.get('errorCode') or entry.get('errorCode'),'rpaStatus':entry.get('rpaStatus'),
                         'rpaWave':entry.get('rpaWave'),'taskId':entry.get('taskId')})
    selected=batch.get('selectedCount',len(entries))
    if type(selected) is not int or selected!=len(entries):raise ProbeError('batch_status_invalid')
    if counts['failed']:cv_status='failed'
    elif counts['interrupted']:cv_status='interrupted'
    elif counts['unconfirmed']:cv_status='unconfirmed'
    elif counts['running']:cv_status='running'
    elif selected and counts['succeeded']==selected:cv_status='succeeded'
    elif counts['succeeded']:cv_status='partial'
    else:cv_status='not_run'
    status=batch.get('status');pid=batch.get('pid');alive=None
    if type(pid) is int and pid>0:alive=recorded_process_alive({'pid':pid,'workerStartTicks':batch.get('processStartTicks')})
    if cv_status in ('failed','interrupted'):status=cv_status
    elif status=='running' and alive is False:status='interrupted'
    elif status in ('succeeded','partial') and cv_status!='succeeded':status='unconfirmed'
    total_shots=sum(e['cv'].get('shotCount') or 0 for e in observed if e['cvStatus']=='succeeded')
    if any(e['cvStatus']=='succeeded' and e['cv'].get('shotCount') is None for e in observed):total_shots=None
    acquired=sum(e['acquisitionStatus']=='video_ready' for e in observed)
    return {'mode':'batch','batchId':batch.get('batchId'),'packageVersion':batch.get('packageVersion'),
            'status':status,'savedStatus':batch.get('status'),'stage':batch.get('stage') or ('complete' if batch.get('status') in ('succeeded','partial') else 'cv'),
            'pid':pid,'processAlive':alive,'errorCode':batch.get('errorCode') or next((e['errorCode'] for e in observed if e.get('errorCode')),None),
            'requestedCount':batch.get('requestedCount'),'selectedCount':selected,'acquiredCount':acquired,
            'completedCount':batch.get('completedCount',0),'shortageCount':batch.get('shortageCount',0),
            'cv':{'status':cv_status,'completedCount':counts['succeeded'],'failedCount':counts['failed'],
                  'runningCount':counts['running'],'pendingCount':counts['pending'],'interruptedCount':counts['interrupted'],
                  'unconfirmedCount':counts['unconfirmed'],'shotCount':total_shots},
            'rpaConcurrency':batch.get('rpaConcurrency',1),'mediaConcurrency':batch.get('mediaConcurrency',1),
            'cvConcurrency':batch.get('cvConcurrency',1),'acquisitionPhase':batch.get('acquisitionPhase'),
            'rpaSubmissionCount':batch.get('rpaSubmissionCount'),'rpaWaves':batch.get('rpaWaves'),
            'firstBatchCsvGate':batch.get('firstBatchCsvGate'),'entries':observed,'report':batch.get('report'),
            'nextAction':'wait_for_batch' if status=='running' else 'view_report' if status in ('succeeded','partial') else 'inspect_saved_state_no_automatic_retry',
            'verification':'read_only_status_metadata_not_artifact_revalidation'}
