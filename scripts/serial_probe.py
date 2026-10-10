"""Bounded serial acceptance queue over existing A inputs; never acquires data."""
from pathlib import Path
import os
import uuid
from probe_core import ROOT, ProbeError, external_root, read, write, digest, resource_summary, safe_error
from runtime_memory import StageMonitor, release_item, memory_stop_code


def probe_batch(manifest_file, output, *, delivery_mode='html'):
    if delivery_mode not in ('html','audit'):raise ProbeError('batch_delivery_invalid')
    manifest_file=Path(manifest_file)
    if manifest_file.stat().st_size>65536:raise ProbeError('batch_manifest_limit')
    manifest=read(manifest_file)
    if not isinstance(manifest,dict) or set(manifest)!={'schemaVersion','runs'} or manifest['schemaVersion']!=1:
        raise ProbeError('batch_manifest_invalid')
    runs=manifest['runs']
    if not isinstance(runs,list) or not 1<=len(runs)<=10:raise ProbeError('batch_manifest_limit')
    roots=[]
    for item in runs:
        if not isinstance(item,dict) or set(item)!={'runDir'} or not isinstance(item['runDir'],str) or not Path(item['runDir']).is_absolute():
            raise ProbeError('batch_manifest_invalid')
        root=external_root(item['runDir'])
        if not root.is_dir():raise ProbeError('batch_input_missing')
        # Pure local schema/platform check; no authorization lookup or acquisition.
        __import__('platform_adapter').validate(read(root/'request.json'))
        roots.append(root)
    output=external_root(output)
    if any(output.is_relative_to(root) or root.is_relative_to(output) for root in roots):raise ProbeError('batch_output_overlap')
    output.mkdir(parents=True,exist_ok=False)
    batch_id='serial-'+uuid.uuid4().hex[:12]
    entries=[{'index':i,'runDir':str(root),'attemptId':batch_id+'-'+str(i),'status':'pending','cvStatus':'pending'} for i,root in enumerate(roots,1)]
    result={'schemaVersion':1,'packageVersion':read(ROOT/'config/platform.json')['version'],
            'platform':read(ROOT/'config/platform.json')['platform'],'batchId':batch_id,'runDir':str(output),'status':'running','stage':'cv_precheck','pid':os.getpid(),
            'manifestSha256':digest(manifest_file),'concurrency':1,'acquisition':'reused_A_only',
            'entries':entries,'completedCount':0,'requestedCount':len(entries)}
    write(output/'batch.json',result)
    monitor=StageMonitor(output,'batch_precheck')
    try:
        from cv_probe import probe_cv, verify_cv,process_identity
        result['processStartTicks']=process_identity(result['pid']);write(output/'batch.json',result)
        from delivery import export_report
        from visual_report import snapshot_report, snapshot_pending_entries, export_batch_html
        with monitor:
            for entry,root in zip(entries,roots):
                monitor.checkpoint('batch_cv_'+str(entry['index']))
                result['stage']='cv';entry.update(status='running',cvStatus='running');write(output/'batch.json',result)
                probe_cv(root,attempt_id=entry['attemptId'],backend='ffmpeg-scene',_defer_report=True)
                receipt=read(root/'cv'/entry['attemptId']/'receipt.json')
                entry.update(cvStatus=receipt['status'],inputVideoSha256=receipt['inputVideoSha256'],
                             workerExitCode=receipt['workerExitCode'],processCleanup=receipt['processCleanup'],
                             memoryGuardReason=receipt.get('memoryGuard',{}).get('reason'))
                if receipt['status']!='succeeded':raise ProbeError(receipt.get('errorCode') or 'batch_cv_failed')
                if receipt['processCleanup']['status']!='completed':raise ProbeError('process_cleanup_unconfirmed')
                verify_cv(root,entry['attemptId'])
                entry['status']='succeeded';result['completedCount']+=1
                entry.update(snapshot_report(root,output/'snapshots'/('item-'+str(entry['index'])),expected_attempt=entry['attemptId']))
                entry['memoryObservation']=resource_summary(root/'cv'/entry['attemptId'])
                write(output/'batch.json',result)
                release_item(root,'batch_item_complete',attempt_id=entry['attemptId'],report_root=entry['reportSnapshot'])
                monitor.checkpoint('batch_item_complete_'+str(entry['index']))
            result.update(status='succeeded',stage='delivery');write(output/'batch.json',result)
            if delivery_mode=='html':
                result['report']=export_batch_html(output,output/'index.html')
            else:
                # Audit assembly starts only after the full CV queue is complete.
                for entry,root in zip(entries,roots):
                    monitor.checkpoint('batch_export_'+str(entry['index']))
                    entry['export']=export_report(root,output/('item-'+str(entry['index'])),expected_attempt=entry['attemptId'],_report_snapshot=entry)
                    write(output/'batch.json',result)
        monitor.check()
        result.update(status='succeeded',stage='complete')
    except Exception as exc:
        result.update(status='failed',errorCode=getattr(exc,'code','batch_failed'),message=safe_error(exc))
        for entry in entries:
            if entry['status']=='running':entry.update(status='failed',cvStatus='failed',errorCode=result['errorCode'])
        if memory_stop_code(result['errorCode']):
            failed=next((e for e in entries if e.get('cvStatus')=='failed' and e.get('memoryGuardReason')), {})
            result['memoryStopReason']=failed.get('memoryGuardReason') or result['errorCode']
            result['memoryStopOrigin']='cv_attempt' if result['stage']=='cv' else 'phase_admission'
            result['automaticReportSkippedReason']='process_cleanup_unconfirmed' if result['errorCode']=='process_cleanup_unconfirmed' else 'memory_guard_stopped'
        if monitor.failure is None and not memory_stop_code(result['errorCode']) and delivery_mode=='html':
            try:
                snapshot_pending_entries(output,entries);write(output/'batch.json',result)
                result['report']=export_batch_html(output,output/'index.html')
            except Exception as report_exc:result['reportErrorCode']=getattr(report_exc,'code','report_failed')
    finally:
        result['distinctVideoCount']=len({e['inputVideoSha256'] for e in entries if e.get('inputVideoSha256')})
        result['guardStopReason']=monitor.failure or result.get('memoryStopReason')
        if monitor.failure:result['guardStopOrigin']='queue_monitor'
        elif result.get('memoryStopOrigin'):result['guardStopOrigin']=result['memoryStopOrigin']
        result['memoryObservation']=resource_summary(output)
        result['acceptanceNote']='Repeated identical video hashes prove repetition only; diverse-video batch and manual quality require separate evidence.'
        write(output/'status.json',{'status':result['status'],'stage':'batch_complete'})
        write(output/'batch.json',result)
    return result
