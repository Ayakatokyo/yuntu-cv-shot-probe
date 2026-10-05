"""Yuntu sample: persisted ranking -> one detail CSV -> verified video URL."""
from copy import deepcopy
from config_specs import resolve_query_spec, query_to_rpa_params, detail_to_rpa_params
from material_field_registry import default_material_field_registry
from material_list_selection import select_materials
from rpa_io import parse_csv_records
from yuntu_normalizer import normalize_list_records, normalize_detail_records
from probe_core import ProbeError, resource_id, write, artifact

LIST_CODE='rpa.conn.juliang.yt.industry.content.rankings.list'
DETAIL_CODE='rpa.conn.juliang.yt.industry.content.rankings.details'

def validate(raw):
    if not isinstance(raw,dict) or set(raw)-{'rpa_shop','query_spec'}:raise ProbeError('request_invalid')
    spec=resolve_query_spec(deepcopy(raw.get('query_spec')))
    if not 1<=spec['collection']['target_top_n']<=10:raise ProbeError('batch_count_invalid')
    return {'rpa_shop':resource_id(raw.get('rpa_shop')),'query_spec':spec}

def select_many(request,root,gateway):
    spec=request['query_spec'];params=query_to_rpa_params(spec)
    for key in ('ages','genders','crowd_groups','brands'):
        if isinstance(params.get(key),list):params[key]=','.join(params[key])
    path=gateway.csv('list',LIST_CODE,params,request['rpa_shop'])
    records=normalize_list_records(parse_csv_records(path),source_path=str(path.relative_to(root)))
    ids=[r['material_id'] for r in records]
    if len(ids)!=len(set(ids)):raise ProbeError('list_duplicate_identity')
    write(root/'acquisition/list-records.json',records)
    write(root/'acquisition/selection-source.json',artifact(path,root))
    selected=select_materials(records,spec['material_list'],default_material_field_registry())
    if not selected:raise ProbeError('selection_empty')
    result=[]
    for material in selected[:count(request)]:
        params=detail_to_rpa_params(spec);params['material_id']=material['material_id']
        result.append((material,params))
    return result

def video_source(csv_path,material,params):
    rows=parse_csv_records(csv_path)
    if not rows or any(r.get('__parse_failed_fields__') for r in rows):raise ProbeError('csv_parse_failed')
    candidates=[]
    for index,raw in enumerate(rows):
        core=raw.get('coreData') if isinstance(raw.get('coreData'),dict) else {}
        ids=[raw.get(k) for k in ('materialId','material_id','coreData.materialId','coreData.objectId') if raw.get(k) not in (None,'')]+[core.get(k) for k in ('objectId','materialId') if core.get(k) not in (None,'')]
        if not ids or any(str(v)!=material['material_id'] for v in ids):raise ProbeError('csv_identity_mismatch')
        detail=normalize_detail_records(raw,material_id=material['material_id'],source_path=str(csv_path.name),expected_context=params)
        fields=[(key,raw.get(key)) for key in ('videoUrl','video_url','coreData.videoUrl','core_data.videoUrl')]+[('coreData.videoUrl',core.get('videoUrl'))]
        urls={str(v).strip() for _,v in fields if v not in (None,'')}
        if len(urls)>1:raise ProbeError('video_url_conflicting')
        if detail.get('video_url'):
            field=next((k for k,v in fields if str(v or '').strip()==detail['video_url']),'video_url')
            candidates.append((index,detail['video_url'],field))
    if not candidates or len({v for _,v,_ in candidates})!=1:raise ProbeError('video_url_missing_or_conflicting')
    index,url,field=candidates[0]
    return {'materialId':material['material_id'],'url':url,'csvPath':str(csv_path.name),'recordIndex':index,'fieldPath':field,'identityStatus':'matched','periodStatus':'matched','expectedMedia':{'durationSec':material.get('video_duration')}}

def count(request):return request['query_spec']['collection']['target_top_n']

def select(request,root,gateway):
    if count(request)!=1:raise ProbeError('use_run_batch')
    return select_many(request,root,gateway)[0]
