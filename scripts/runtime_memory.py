"""Per-run phase admission and best-effort release of completed owned files.
These are Skill policies; no sandbox limits or global caches are changed.
"""
import gc
import hashlib
import json
import os
from pathlib import Path
import stat
import time
import threading
from memory_guard import evaluate_guard, process_tree_rss


def policy():
    from probe_core import ROOT, read, ProbeError
    value=read(ROOT/'config/memory-policy.json')
    if value.get('schemaVersion')!=1 or set(value.get('stageReserveMiB',{}))!={'selection','detail_rpa','video_download','media_probe','cv_precheck','export'}:
        raise ProbeError('memory_policy_invalid')
    for reserve in value['stageReserveMiB'].values():
        if not isinstance(reserve,int) or isinstance(reserve,bool) or not 16<=reserve<=512:raise ProbeError('memory_policy_invalid')
    return value


def append_event(root, name, value):
    with (Path(root)/name).open('a',encoding='utf-8') as handle:
        handle.write(json.dumps({'time':time.time(),**value},ensure_ascii=False)+'\n')


def check_stage(root, stage):
    from probe_core import ROOT, read, write, cgroup_snapshot, ProbeError
    config=read(ROOT/'config/cv-low-memory.json')
    result=evaluate_guard(cgroup_snapshot(),config,tree_rss=process_tree_rss(os.getpid()),reserve_mib=policy()['stageReserveMiB'][stage])
    result['stage']=stage
    append_event(root,'phase-memory.ndjson',result)
    write(Path(root)/'phase-memory.json',result)
    if result['abort']:raise ProbeError('insufficient_stage_headroom')
    return result


def release_completed(root, stage):
    """Only regular CSV/JSON/JSONL/video files in this run; failures are evidence.
    DONTNEED is advisory and does not promise a cgroup reduction.
    """
    root=Path(root).resolve()
    paths=[]
    for folder in ('acquisition','media'):
        directory=root/folder
        if directory.is_dir() and not directory.is_symlink():
            paths.extend(p for p in sorted(directory.rglob('*')) if p.suffix in ('.csv','.json','.jsonl','.mp4'))
    return release_owned(root,stage,root,paths)


def release_owned(log_root, stage, owner_root, paths):
    """Advise an explicit list of completed files created/owned by this operation.
    Never scan an export parent, follow symlinks, remove files, or clear global caches.
    """
    from probe_core import cgroup_snapshot
    owner=Path(owner_root).absolute();root=owner.resolve();before=cgroup_snapshot()
    result={'stage':stage,'policyOrigin':'skill','supported':hasattr(os,'posix_fadvise') and hasattr(os,'POSIX_FADV_DONTNEED'),
            'attemptedFiles':0,'advisedBytes':0,'errors':[], 'before':before,
            'effect':'advisory_only_not_guaranteed_reclaim'}
    if result['supported'] and not owner.is_symlink():
        for original in dict.fromkeys(Path(p).absolute() for p in paths):
            if not original.is_relative_to(owner):continue
            relative=original.relative_to(owner)
            path=root/relative
            if '..' in relative.parts:continue
            if any((root/Path(*relative.parts[:i])).is_symlink() for i in range(1,len(relative.parts)+1)):continue
            fd=None
            try:
                if not stat.S_ISREG(path.lstat().st_mode):continue
                fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
                info=os.fstat(fd)
                if not stat.S_ISREG(info.st_mode):continue
                result['attemptedFiles']+=1
                os.fsync(fd)
                os.posix_fadvise(fd,0,0,os.POSIX_FADV_DONTNEED)
                result['advisedBytes']+=info.st_size
            except OSError as exc:
                result['errors'].append({'path':path.relative_to(root).as_posix(),'errno':exc.errno})
            finally:
                if fd is not None:os.close(fd)
    result['after']=cgroup_snapshot()
    append_event(log_root,'cache-advice.ndjson',result)
    return result


def digest_owned(path, *, owner_root, log_root, stage, chunk_bytes=1024*1024):
    """Complete SHA-256 with bounded, advisory release of this explicit input.
    Do not use this for executables/dependencies. DONTNEED is not a reclaim guarantee.
    """
    from probe_core import ProbeError, cgroup_snapshot
    owner=Path(owner_root).absolute();original=Path(path).absolute()
    if owner.is_symlink():raise ProbeError('unsafe_artifact_path')
    root=owner.resolve()
    if not original.is_relative_to(owner):raise ProbeError('unsafe_artifact_path')
    relative=original.relative_to(owner)
    if '..' in relative.parts or any((root/Path(*relative.parts[:i])).is_symlink() for i in range(1,len(relative.parts)+1)):
        raise ProbeError('unsafe_artifact_path')
    page=os.sysconf('SC_PAGESIZE') if hasattr(os,'sysconf') else 4096
    if not isinstance(chunk_bytes,int) or isinstance(chunk_bytes,bool) or chunk_bytes<page or chunk_bytes%page:
        raise ProbeError('cache_hash_chunk_invalid')
    target=root/relative;before=cgroup_snapshot()
    result={'stage':stage,'policyOrigin':'skill','operation':'owned_input_sha256','path':relative.as_posix(),
            'supported':hasattr(os,'posix_fadvise') and hasattr(os,'POSIX_FADV_DONTNEED'),
            'attemptedFiles':1,'advisedBytes':0,'hashedBytes':0,'errors':[],'before':before,
            'effect':'advisory_only_not_guaranteed_reclaim'}
    fd=None;sha=hashlib.sha256();error=None
    def advise(offset,length):
        try:os.posix_fadvise(fd,offset,length,os.POSIX_FADV_DONTNEED)
        except OSError as exc:
            if not result['errors']:result['errors'].append({'path':relative.as_posix(),'errno':exc.errno})
            return False
        return True
    try:
        if not stat.S_ISREG(target.lstat().st_mode):raise ProbeError('artifact_missing')
        fd=os.open(target,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        initial=os.fstat(fd)
        result['initialFileStat']={'device':initial.st_dev,'inode':initial.st_ino,'sizeBytes':initial.st_size,'modifiedNs':initial.st_mtime_ns}
        if not stat.S_ISREG(initial.st_mode):raise ProbeError('artifact_missing')
        can_advise=result['supported']
        if can_advise:
            try:os.fsync(fd)
            except OSError as exc:
                result['errors'].append({'path':relative.as_posix(),'errno':exc.errno});can_advise=False
        while True:
            chunk=os.read(fd,chunk_bytes)
            if not chunk:break
            sha.update(chunk);result['hashedBytes']+=len(chunk)
            # Only complete pages during the stream; EOF advice includes the tail.
            end=result['hashedBytes']//page*page;offset=result['advisedBytes'];length=end-offset
            if can_advise and length:
                if advise(offset,length):result['advisedBytes']+=length
                else:can_advise=False
            del chunk
        final=os.fstat(fd)
        result['finalFileStat']={'device':final.st_dev,'inode':final.st_ino,'sizeBytes':final.st_size,'modifiedNs':final.st_mtime_ns}
        path_stat=target.lstat()
        identity=lambda info:(info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns)
        if identity(initial)!=identity(final) or identity(initial)!=identity(path_stat) or result['hashedBytes']!=initial.st_size:
            raise ProbeError('artifact_changed')
        if can_advise and advise(0,0):result['advisedBytes']=result['hashedBytes']
        result['sha256']=sha.hexdigest()
    except Exception as exc:
        error=exc;result['errorCode']=getattr(exc,'code','owned_hash_failed')
    finally:
        if fd is not None:os.close(fd)
        result['after']=cgroup_snapshot();append_event(log_root,'cache-advice.ndjson',result)
    if error:raise error
    return result['sha256']


def release_item(root, stage, *, attempt_id=None, report_root=None):
    """Release explicit completed A/attempt/snapshot files and collect Python garbage.
    The receipt provides the attempt file set, so no prior attempt is scanned.
    """
    from probe_core import read, cgroup_snapshot
    root=Path(root);events=[release_completed(root,stage+'_inputs')]
    if attempt_id:
        folder=root/'cv'/attempt_id;receipt=folder/'receipt.json'
        if receipt.is_file():
            data=read(receipt)
            if data.get('processCleanup',{}).get('status')=='completed':
                paths=[folder/item['path'] for item in data.get('artifacts',[])]+[receipt]
                events.append(release_owned(root,stage+'_attempt',folder,paths))
            else:
                append_event(root,'cache-advice.ndjson',{'stage':stage+'_attempt','operation':'attempt_release_skipped','reason':'process_cleanup_unconfirmed'})
    if report_root:
        snapshot=Path(report_root)
        events.append(release_owned(root,stage+'_snapshot',snapshot,[snapshot/'report/report.json',snapshot/'report/receipt.json']))
    before=cgroup_snapshot();collected=gc.collect()
    result={'stage':stage+'_python_gc','operation':'gc_collect','collectedObjects':collected,'before':before,
            'after':cgroup_snapshot(),'effect':'advisory_only_not_guaranteed_reclaim'}
    append_event(root,'cache-advice.ndjson',result);return {'files':events,'pythonGc':result}


def memory_stop_code(code):
    return code in {'memory_guard_aborted','insufficient_headroom','insufficient_stage_headroom','operation_memory_guard_aborted','memory_monitor_failed','process_cleanup_unconfirmed'}


class StageMonitor:
    """Sample a separate operation directory every 200ms; latch stop decisions.
    The caller checks at bounded I/O chunks and stage boundaries. Sampling cannot
    guarantee interception of instantaneous OOM, and does not kill other tasks.
    """
    def __init__(self, root, stage):
        from probe_core import ROOT, Resources, read, cgroup_snapshot
        self.root=Path(root);self.stage=stage
        self.config=read(ROOT/'config/cv-low-memory.json')
        self.baseline=cgroup_snapshot();self.sampler=Resources(self.root,interval=.2)
        self.stop=threading.Event();self.lock=threading.Lock();self.failure=None;self.thread=None

    def observe(self):
        from probe_core import write
        with self.lock:
            row=self.sampler.sample()
            guard=evaluate_guard(row['cgroup'],self.config,baseline=self.baseline,tree_rss=row['processTreeSampledRssBytes'])
            guard['stage']=row['stage']
            append_event(self.root,'guard-samples.ndjson',guard)
            write(self.root/'memory-guard.json',guard)
            if guard['abort'] and self.failure is None:self.failure=guard['reason']

    def check(self):
        from probe_core import ProbeError
        if self.failure:raise ProbeError('operation_memory_guard_aborted')

    def checkpoint(self, phase):
        from probe_core import write
        write(self.root/'status.json',{'status':'running','stage':phase,'pid':os.getpid()})
        self.observe();self.check()

    def loop(self):
        while not self.stop.wait(.2):
            try:self.observe()
            except Exception:self.failure='memory_monitor_failed';return

    def __enter__(self):
        self.checkpoint(self.stage)
        self.thread=threading.Thread(target=self.loop,daemon=True);self.thread.start()
        return self

    def __exit__(self,*args):
        self.stop.set()
        if self.thread:self.thread.join()
        self.observe()
