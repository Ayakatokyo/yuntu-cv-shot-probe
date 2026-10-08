"""Skill-owned guard: conservative inactive-file credit plus independent ceilings.
No cgroup writes, cache clearing, or kernel-limit changes. Estimates are not free RAM.
"""
from pathlib import Path
import math
import re
import subprocess
import sys

def values(raw):
    result={};invalid=set()
    for line in (raw or '').splitlines():
        parts=line.split()
        if len(parts)!=2:continue
        key=parts[0].rstrip(':')
        if key in result or key in invalid:
            result.pop(key,None);invalid.add(key);continue
        if not re.fullmatch(r'[0-9]+',parts[1]):invalid.add(key);continue
        result[key]=int(parts[1])
    return result


def parse_native_meminfo(raw):
    """Only the two needed native-proc counters; bytes, never missing-as-zero."""
    result={};seen=set()
    for line in (raw or '').splitlines():
        parts=line.split();key=parts[0].rstrip(':') if parts else ''
        if key not in ('Dirty','Writeback'):continue
        if key in seen or len(parts)!=3 or parts[0]!=key+':' or parts[2]!='kB' or not re.fullmatch(r'[0-9]+',parts[1]):
            raise ValueError('native_meminfo_invalid')
        seen.add(key);result[key]=int(parts[1])*1024
    if seen!={'Dirty','Writeback'}:raise ValueError('native_meminfo_missing_fields')
    return result


def global_deduction_bounds(snapshot):
    evidence=snapshot.get('nativeProcMeminfo') or {};source=evidence.get('source') or {}
    if evidence.get('status')!='available' or source!={'path':'/proc/meminfo','fstype':'proc','mountRoot':'/','mountPoint':'/proc'}:return {}
    try:
        before=parse_native_meminfo(evidence['before']);after=parse_native_meminfo(evidence['after'])
        bounds={key:max(before[key],after[key]) for key in before}
        if evidence.get('upperBoundsBytes')!=bounds:return {}
    except (KeyError,TypeError,ValueError):return {}
    return bounds


def process_tree_rss(pid):
    try:
        processes={}
        if sys.platform=='darwin':
            observed=subprocess.run(['ps','-axo','pid=,ppid=,rss='],capture_output=True,text=True,timeout=2)
            if observed.returncode:return None
            for line in observed.stdout.splitlines():
                child,parent,rss=map(int,line.split())
                processes[child]=(parent,rss*1024)
        else:
            for directory in Path('/proc').iterdir():
                if not directory.name.isdigit():continue
                try:
                    fields=values((directory/'status').read_text().replace(' kB',''))
                    processes[int(directory.name)]=(fields['PPid'],fields.get('VmRSS',0)*1024)
                except (OSError,KeyError):continue
        included={pid};changed=True
        while changed:
            changed=False
            for child,(parent,rss) in processes.items():
                if parent in included and child not in included:included.add(child);changed=True
        return sum(processes[p][1] for p in included if p in processes) if pid in processes else None
    except (OSError, ValueError, subprocess.TimeoutExpired):return None

def evaluate_guard(snapshot,config,*,baseline=None,tree_rss=None,reserve_mib=0):
    reserve=reserve_mib*1048576;tree_budget=config['maxProcessTreeRssMiB']*1048576
    result={'policyVersion':'0.5.5-cache-backed-admission','policyOrigin':'skill','limitOrigin':'sandbox_cgroup','abort':False,'reason':'unknown_cgroup',
            'headroomKnown':False,'stageReserveBytes':reserve,'processTreeRssBytes':tree_rss,'processTreeBudgetBytes':tree_budget,
            'workingSetFraction':config['memoryGuardFraction'],'rawEmergencyFraction':config['memoryHardFraction'],
            'reclaimEstimate':'conservative inactive_file credit; not guaranteed reclaimable/free RAM',
            'cacheBackedAdmission':{'eligible':False,'used':False,'reasons':['unknown_cgroup']}}
    tree_known=type(tree_rss) is int and tree_rss>=0
    if tree_known and tree_rss>tree_budget:result.update(abort=True,reason='process_tree_budget')
    keys=('memory.current','memory.max') if snapshot.get('version')==2 else ('memory.usage_in_bytes','memory.limit_in_bytes')
    try:
        if any(not re.fullmatch(r'[0-9]+',str(snapshot[k])) for k in keys):return result
        used,limit=(int(snapshot[k]) for k in keys)
    except (KeyError,ValueError,TypeError):return result
    if snapshot.get('status')!='available' or limit<=0 or limit>=2**60:return result
    stats=values(snapshot.get('memory.stat'));v2=snapshot.get('version')==2
    has_total=any(line.split() and line.split()[0].startswith('total_') for line in (snapshot.get('memory.stat') or '').splitlines())
    prefix='total_' if not v2 and has_total else ''
    inactive=stats.get(prefix+'inactive_file');cache=stats.get('file' if v2 else prefix+'cache')
    deduction_keys=['shmem','file_dirty','file_writeback'] if v2 else [prefix+'shmem',prefix+'dirty',prefix+'writeback']
    required=deduction_keys if v2 else deduction_keys[1:]
    missing=[key for key in deduction_keys if key not in stats]
    inputs={};sources={};bounds=global_deduction_bounds(snapshot) if not v2 else {}
    for key in required:
        if key in stats:inputs[key]=stats[key];sources[key]='memory.stat_same_scope'
        elif bounds:
            native_key='Dirty' if key.endswith('dirty') else 'Writeback'
            inputs[key]=bounds[native_key];sources[key]='native_proc_global_upper_bound'
    unresolved=[key for key in required if key not in inputs]
    credit=0;basis='raw_usage_fallback'
    if inactive is not None and cache is not None and not unresolved:
        credit=max(0,min(inactive,cache,used)-sum(inputs.values()))
        basis='usage_minus_inactive_file_with_global_upper_bounds' if 'native_proc_global_upper_bound' in sources.values() else 'usage_minus_conservative_inactive_file'
    working=used-credit;raw_headroom=max(0,int(limit*config['memoryHardFraction'])-used)
    stage_headroom=max(0,min(int(limit*config['memoryHardFraction'])-(working if credit>0 else used),int(limit*config['memoryGuardFraction'])-working))
    tree_headroom=max(0,tree_budget-tree_rss) if tree_known else None
    pressure_full=None
    full_lines=[line for line in (snapshot.get('memory.pressure') or '').splitlines() if line.startswith('full ')]
    if len(full_lines)==1:
        try:
            candidate=float(next(p.split('=',1)[1] for p in full_lines[0].split() if p.startswith('avg10=')))
            if math.isfinite(candidate) and candidate>=0:pressure_full=candidate
        except (StopIteration,ValueError):pass
    def pressure_total(observed):
        lines=[line for line in (observed.get('memory.pressure') or '').splitlines() if line.startswith('full ')]
        if len(lines)!=1:return None
        matches=[part.split('=',1)[1] for part in lines[0].split() if part.startswith('total=')]
        return int(matches[0]) if len(matches)==1 and re.fullmatch(r'[0-9]+',matches[0]) else None
    current_total=pressure_total(snapshot);baseline_total=pressure_total(baseline or {})
    pressure_delta=max(0,current_total-baseline_total) if current_total is not None and baseline_total is not None else None
    pressure_regressed=current_total is not None and baseline_total is not None and current_total<baseline_total
    fail_known=False;fail_delta=0
    if baseline and not v2 and baseline.get('status')=='available' and baseline.get('version')==1 and baseline.get('memory.limit_in_bytes')==snapshot.get('memory.limit_in_bytes'):
        current=values('fail '+str(snapshot.get('memory.failcnt'))).get('fail')
        prior_fail=values('fail '+str(baseline.get('memory.failcnt'))).get('fail')
        if current is not None and prior_fail is not None and current>=prior_fail:
            fail_known=True;fail_delta=current-prior_fail
    oom=values(snapshot.get('memory.oom_control')).get('under_oom') if not v2 else None
    under_oom=(oom==1) if oom in (0,1) else None
    events=values(snapshot.get('memory.events'));prior=values((baseline or {}).get('memory.events'))
    events_delta={key:max(0,value-prior.get(key,value)) for key,value in events.items()}
    events_raised=fail_delta>0 or any(events_delta.get(key,0)>0 for key in ('oom','oom_kill','max'))
    raw_exceeded=used>=limit*config['memoryHardFraction']
    reasons=[]
    if v2:reasons.append('v1_required')
    if credit<=0:reasons.append('positive_verified_credit_required')
    if working>=limit*config['memoryGuardFraction']:reasons.append('working_set_ceiling')
    if stage_headroom<reserve:reasons.append('insufficient_stage_headroom')
    if not tree_known:reasons.append('process_tree_rss_unknown')
    elif tree_headroom<reserve or tree_rss>=tree_budget:reasons.append('insufficient_process_stage_headroom')
    if not fail_known:reasons.append('failcnt_baseline_unknown')
    elif events_raised:reasons.append('shared_cgroup_limit_event')
    if under_oom is not False:reasons.append('under_oom_or_unknown')
    if pressure_full is not None and pressure_full>=1 or pressure_delta is not None and pressure_delta>0:reasons.append('shared_cgroup_pressure')
    if pressure_regressed:reasons.append('pressure_counter_regressed')
    if used>=limit:reasons.append('sandbox_limit_reached')
    eligible=not reasons
    result.update(reason=result['reason'] if result['abort'] else 'within_skill_budget',headroomKnown=True,
                  headroomToSkillRawCeilingBytes=raw_headroom,headroomForStageBytes=stage_headroom,
                  headroomBasis='conservative_working_set_estimate' if credit>0 else 'raw_usage',processTreeHeadroomBytes=tree_headroom,
                  rawUsageBytes=used,sandboxLimitBytes=limit,inactiveFileCreditBytes=credit,workingSetEstimateBytes=working,
                  guardBasis=basis,memoryStat=stats,missingReclaimDeductionFields=missing,unresolvedReclaimDeductionFields=unresolved,
                  reclaimDeductionBytes=inputs,reclaimDeductionSources=sources,
                  shmemDeduction='required_v2' if v2 else 'not_required_native_v1_file_lru',nativeProcMeminfo=snapshot.get('nativeProcMeminfo'),
                  pressureFullAvg10=pressure_full,pressureFullTotalDelta=pressure_delta,pressureCounterRegressed=pressure_regressed,pressureStatus='available' if pressure_full is not None else 'unknown',
                  failcntKnown=fail_known,failcntDelta=fail_delta,underOom=under_oom,eventDelta=events_delta,
                  rawCeilingExceeded=raw_exceeded,cacheBackedAdmission={'eligible':eligible,'used':raw_exceeded and eligible,'reasons':reasons})
    if not result['abort']:
        reason=None
        if used>=limit:reason='raw_emergency_ceiling'
        elif events_raised:reason='shared_cgroup_limit_event'
        elif under_oom is True:reason='shared_cgroup_current_oom'
        elif pressure_full is not None and pressure_full>=1 and used>=limit*.85:reason='shared_cgroup_pressure'
        elif raw_exceeded and pressure_delta is not None and pressure_delta>0:reason='shared_cgroup_pressure'
        elif raw_exceeded and not eligible:reason='raw_emergency_ceiling'
        elif working>=limit*config['memoryGuardFraction']:reason='working_set_ceiling'
        elif stage_headroom<reserve:reason='insufficient_stage_headroom'
        elif tree_known and tree_headroom<reserve:reason='insufficient_process_stage_headroom'
        if reason:result.update(abort=True,reason=reason)
    return result
