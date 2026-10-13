"""Check proposed schemas, synthetic fixtures and selected semantic invariants.

This is a specification check, not an implementation of the prediction algorithm.
Run: python checks/check_contracts.py --report checks/contracts_report.json
"""
from __future__ import annotations
import argparse
import copy
import json
import math
from pathlib import Path
from typing import Any, Callable
from importlib.metadata import version
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]

def load(rel: str) -> Any:
    with (ROOT/rel).open(encoding='utf-8') as fh:
        return json.load(fh)

def validate_trajectory(payload: dict[str, Any]) -> None:
    for tid, track in payload['uavs_coords_str'].items():
        lengths = [len(track[k]) for k in ('lngs','lats','ts')]
        if 'alts' in track:
            lengths.append(len(track['alts']))
        if len(set(lengths)) != 1:
            raise ValueError(f'{tid}: unequal array lengths')
        ts = track['ts']
        if any(b <= a for a, b in zip(ts, ts[1:])):
            raise ValueError(f'{tid}: timestamps must strictly increase in STRICT_API mode')
        for key in ('lngs','lats','alts'):
            if key in track and any(not math.isfinite(v) for v in track[key]):
                raise ValueError(f'{tid}: nonfinite coordinates')

def validate_groups(payload: dict[str, Any], tracks: dict[str, Any]) -> None:
    seen, ids = set(), set()
    for group in payload['groups']:
        if group['groupId'] in ids:
            raise ValueError('duplicate group ID within snapshot')
        ids.add(group['groupId'])
        for member in group['memberIds']:
            if member not in tracks:
                raise ValueError('group references missing member')
            if member in seen:
                raise ValueError('member assigned to more than one group')
            seen.add(member)

def validate_output(payload: dict[str, Any]) -> None:
    for group in payload['groups']:
        if group['groupSize'] != len(group['memberIds']):
            raise ValueError('groupSize does not match memberIds')
        probs = [group['unresolvedModelProbability']]+[f['destinationProbability'] for f in group['facilityPredictions']]
        if group['status']=='OK_MODEL_OUTPUT':
            if any(p is None for p in probs) or not math.isclose(sum(probs),1.0,abs_tol=1e-9):
                raise ValueError('OK_MODEL_OUTPUT requires a complete normalized model set')
        for facility in group['facilityPredictions']:
            arrival=facility['arrival']
            if arrival['conditionalOnFacilityId'] != facility['facilityId']:
                raise ValueError('conditional time refers to a different facility')
            interval=arrival['intervalSeconds']
            if interval is not None and interval[1]<interval[0]:
                raise ValueError('reversed interval')
            if arrival['status'] in {'CONFIG_REQUIRED','INSUFFICIENT_EVIDENCE','MODEL_MISMATCH','NOT_EVALUATED'}:
                if arrival['etaMedianSeconds'] is not None or arrival['etaMapSeconds'] is not None or interval is not None:
                    raise ValueError('unsupported ETA must be null')
            cells=arrival['timeDistribution']
            if cells:
                mass=sum(c['conditionalMass'] for c in cells)
                if not math.isclose(mass,1.0,abs_tol=1e-9):
                    raise ValueError('conditional time masses must sum to one')
                last=-1.0
                for cell in cells:
                    lo,hi,t=cell['lowerBoundSeconds'],cell['upperBoundSeconds'],cell['representativeSeconds']
                    if not lo<t<hi or lo<last:
                        raise ValueError('invalid or overlapping time cells')
                    last=hi

def expect_error(fn: Callable[[], None]) -> None:
    try:
        fn()
    except (ValueError, TypeError, KeyError):
        return
    raise AssertionError('Expected invalid fixture to fail')

def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument('--report',type=Path)
    args=parser.parse_args()
    results=[]
    def run(name: str, fn: Callable[[], None]) -> None:
        try:
            fn(); results.append({'check':name,'status':'PASS'})
        except Exception as exc:
            results.append({'check':name,'status':'FAIL','error':repr(exc)})
        print(results[-1]['status'],name)
    cases=[('trajectory','trajectory.synthetic'),('airspace','airspace.synthetic'),('groups','groups.synthetic'),('output','output.structure-only')]
    for stem,fixture in cases:
        s=load(f'schemas/{stem}.schema.json')
        run(f'{stem}_schema_and_fixture',lambda s=s,fixture=fixture:(Draft202012Validator.check_schema(s),Draft202012Validator(s).validate(load(f'examples/{fixture}.json'))))
    tr=load('examples/trajectory.synthetic.json')
    gs=load('examples/groups.synthetic.json')
    out=load('examples/output.structure-only.json')
    run('valid_track_semantics',lambda:validate_trajectory(tr))
    run('valid_group_semantics',lambda:validate_groups(gs,tr['uavs_coords_str']))
    run('valid_output_semantics',lambda:validate_output(out))
    bad=copy.deepcopy(tr);bad['uavs_coords_str']['UAV-A']['ts'][1]=bad['uavs_coords_str']['UAV-A']['ts'][0]
    run('duplicate_timestamp_rejected',lambda:expect_error(lambda:validate_trajectory(bad)))
    bad_len=copy.deepcopy(tr);bad_len['uavs_coords_str']['UAV-A']['lngs'].pop()
    run('unequal_lengths_rejected',lambda:expect_error(lambda:validate_trajectory(bad_len)))
    bad_g=copy.deepcopy(gs);bad_g['groups'][1]['memberIds'].append('UAV-A')
    run('overlapping_groups_rejected',lambda:expect_error(lambda:validate_groups(bad_g,tr['uavs_coords_str'])))
    bad_o=copy.deepcopy(out);bad_o['groups'][0]['facilityPredictions'][0]['arrival']['etaMedianSeconds']=42
    run('unsupported_eta_rejected',lambda:expect_error(lambda:validate_output(bad_o)))
    no_alts=copy.deepcopy(tr)
    for t in no_alts['uavs_coords_str'].values():t.pop('alts')
    run('optional_altitudes_supported',lambda:(Draft202012Validator(load('schemas/trajectory.schema.json')).validate(no_alts),validate_trajectory(no_alts)))
    report={'scope':'Proposed schema and selected semantic checks only; not a full service test','package':{'jsonschema':version('jsonschema')},'checks':results,'passed':sum(r['status']=='PASS' for r in results),'total':len(results)}
    if args.report:
        args.report.parent.mkdir(parents=True,exist_ok=True)
        args.report.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    return 0 if report['passed']==report['total'] else 1

if __name__=='__main__':
    raise SystemExit(main())
