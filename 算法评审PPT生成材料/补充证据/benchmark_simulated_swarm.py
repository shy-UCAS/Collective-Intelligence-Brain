"""Reproducible synthetic swarm benchmarks; never changes production algorithms.

Run with the study_flask Conda environment. Output contains inputs, per-call
latencies, correctness comparisons, source hashes and a Chinese report.
"""
from __future__ import annotations

import argparse
import ast
import contextlib
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import inspect
import io
import json
import math
import os
from pathlib import Path
import platform
import statistics
import sys
import threading
import time
from types import SimpleNamespace
from unittest.mock import patch

PROJECT = Path(__file__).resolve().parents[1]
ROOT = PROJECT.parent
sys.path.insert(0, str(PROJECT))
os.chdir(PROJECT)
os.environ['FORMATION_RECOG_DEVICE'] = 'cpu'
os.environ['VECTORIZED_FEATURES'] = '1'

import numpy as np
import torch
import psutil
from flask import Flask
from situation_judgment import register_situation_routes
from situation_judgment import engine as em
from situation_judgment.legacy_adapter import LegacyAlgorithmAdapter
from formation_recognition.clusters_recognition import SplitClusters


def summary(values):
    a = sorted(values)
    return dict(meanMs=statistics.fmean(a), medianMs=statistics.median(a),
                p95Ms=a[math.ceil(.95 * len(a))-1], minMs=a[0], maxMs=a[-1], count=len(a))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def synth(n, window, layout, seed):
    rng = np.random.default_rng(seed)
    # Only geographical background is reused; no identities or whitelist entries.
    template = json.loads((PROJECT/'outputs/agents02_http_request_sample.json').read_text(encoding='utf-8'))
    epoch = 1792717200000
    payload = dict(requestId='synthetic', snapshotTime=datetime.fromtimestamp(epoch/1000, timezone.utc).isoformat(),
                   uavs_coords_str={}, targetAttributes={}, baseData=template['baseData'],
                   options={'returnEvidenceChain': True, 'returnDebug': True},
                   realPersons=[],dronesBySerialNos=[],droneWhitelistDtos=[],flightPlansBySn=[])
    for i in range(n):
        group, member = divmod(i, 5)
        phase = group % 5
        t = np.arange(window, dtype=float) - window + 1
        if layout == 'separated':
            end = np.array([(group % 8)*650 + member*12, (group//8)*650 + (member % 2)*15], dtype=float)
        else:
            end = rng.normal(0, 20, 2)
        heading = .2 if layout == 'dense' else phase*.25
        speed = 12.0 + member*.05
        # Straight, acceleration, turn, stationary and gentle weaving groups.
        factor = 1 + (.002*t if phase == 1 else 0)
        if phase == 3:
            speed = 0.0
        angles = heading + (.004*t if phase == 2 else np.zeros_like(t))
        velocity = np.column_stack([np.cos(angles)*speed*factor, np.sin(angles)*speed*factor])
        xy = np.cumsum(velocity, axis=0)
        xy -= xy[-1]
        xy += end
        if phase == 4:
            xy[:, 1] += 4*np.sin(t*.15)
        xy += rng.normal(0, .04, xy.shape)
        lng = 116.38 + xy[:, 0]/(111320*math.cos(math.radians(39.90)))
        lat = 39.90 + xy[:, 1]/111320
        key = f'sim_{i:04d}'
        payload['uavs_coords_str'][key] = dict(lngs=lng.tolist(), lats=lat.tolist(),
                    ts=(epoch+t*1000).astype(np.int64).tolist(), alts=[80.0]*window)
        payload['targetAttributes'][key] = dict(targetType='uav', payloadType='unknown',
                    altitudeReference='AGL', isCooperative=False)
    return payload


class RssSampler:
    def __enter__(self):
        self.proc = psutil.Process()
        self.start = self.peak = self.proc.memory_info().rss
        self.stop = threading.Event()
        def watch():
            while not self.stop.wait(.005):
                self.peak = max(self.peak, self.proc.memory_info().rss)
        self.thread = threading.Thread(target=watch, daemon=True)
        self.thread.start()
        return self
    def __exit__(self, *_):
        self.peak = max(self.peak, self.proc.memory_info().rss)
        self.stop.set()
        self.thread.join()
    def report(self):
        return dict(startRssMiB=self.start/2**20, sampledPeakRssMiB=self.peak/2**20,
                    sampledGrowthMiB=(self.peak-self.start)/2**20, intervalMs=5)


def timed(fn, repeats=20):
    fn()
    samples = []
    result = None
    for _ in range(repeats):
        start = time.perf_counter()
        result = fn()
        samples.append((time.perf_counter()-start)*1000)
    return summary(samples), result


def partition(groups):
    return sorted(sorted(g) for g in groups)


def brute_groups(targets):
    by_id = {x.target_id:x for x in targets}
    ids = list(by_id)
    seen, groups = set(), []
    for root in sorted(ids):
        if root in seen:
            continue
        group, stack = [], [root]
        seen.add(root)
        while stack:
            current = by_id[stack.pop()]
            group.append(current.target_id)
            for candidate_id in ids:
                if candidate_id in seen:
                    continue
                candidate = by_id[candidate_id]
                close = em._distance(current.point, candidate.point) <= 250
                aligned = current.heading is None or candidate.heading is None or em._angle_delta(current.heading,candidate.heading) <= 50
                if close and aligned:
                    seen.add(candidate_id)
                    stack.append(candidate_id)
        groups.append(group)
    return partition(groups)


def components(out, log):
    results = dict(behavior=[], fallback=[], span=[], dbscan=[])
    adapter = LegacyAlgorithmAdapter()
    engine = em.SituationEngine()
    for n,w in [(10,120),(50,120),(100,120),(200,120),(100,30),(100,240)]:
        tracks = synth(n,w,'separated',20261023)['uavs_coords_str']
        objs = adapter._prepare_tracks(tracks)['objects']
        # Isolate individual features; group shrink/spread is identical code in both paths.
        funcs = [lambda:adapter._extract_behavior_features_legacy(objs,[]),
                 lambda:adapter._extract_behavior_features_vectorized(objs,[])]
        for f in funcs: f()
        samples=[[],[]]
        for rep in range(20):
            for k in ([0,1] if rep%2==0 else [1,0]):
                start=time.perf_counter(); funcs[k](); samples[k].append((time.perf_counter()-start)*1000)
        old,new=funcs[0]()['members'],funcs[1]()['members']
        diffs={field:sum(old[k][field]!=new[k][field] for k in old) for field in next(iter(old.values()))}
        speed_error=max(abs(old[k]['speedMps']-new[k]['speedMps']) for k in old)
        row=dict(n=n,window=w,legacy=summary(samples[0]),vectorized=summary(samples[1]),
                 speedup=statistics.median(samples[0])/statistics.median(samples[1]),
                 differingTargetsByField=diffs,maxSpeedDifferenceMps=speed_error)
        results['behavior'].append(row)
    for layout in ['separated','dense']:
        for n in [10,50,100,200]:
            equality=[]
            for seed in [20261023,20261024,20261025]:
                payload=synth(n,120,layout,seed)
                targets=[]
                for key,tr in payload['uavs_coords_str'].items():
                    targets.append(em.Target(target_id=key,attrs={'targetType':'uav'},
                        points=list(zip(tr['lngs'][-2:],tr['lats'][-2:])),ts=[0,1000],alts=[80.,80.],
                        quality=.9,speed=12.,heading=90.,heading_change=0.,hover_seconds=0.))
                def lightweight(_self,cid,members,*args,**kwargs):
                    return {'clusterId':cid,'targetIds':[x.target_id for x in members]}
                def current():
                    return partition(x['targetIds'] for x in engine._clusters(targets,
                        {'ruleConfig':{'clusterDistanceMeters':250,'clusterHeadingDifferenceDegrees':50}},
                        datetime.now(timezone.utc),legacy_context={'groups':[]}))
                with patch.object(em.SituationEngine,'_evaluate_cluster',new=lightweight):
                    a,old=timed(lambda:brute_groups(targets),20)
                    b,new=timed(current,20)
                equality.append(old==new)
                results['fallback'].append(dict(n=n,layout=layout,seed=seed,brute=a,current=b,
                    path='kdtree' if n>10 else 'brute',samePartition=old==new,
                    groups=len(new),speedup=a['medianMs']/b['medianMs']))
    # Extract the exact production span block by AST, avoiding a hand-rewritten fast path.
    tree=ast.parse(inspect.getsource(em))
    cls=next(x for x in tree.body if isinstance(x,ast.ClassDef) and x.name=='SituationEngine')
    fun=next(x for x in cls.body if isinstance(x,ast.FunctionDef) and x.name=='_compute_member_intent_features')
    block=next(x for x in fun.body if isinstance(x,ast.If) and 'track_span' in ast.unparse(x))
    block_code=compile(ast.fix_missing_locations(ast.Module(body=[block],type_ignores=[])),'production_span_block','exec')
    def fast(points):
        ctx=dict(target=SimpleNamespace(points=points),EARTH_RADIUS_M=em.EARTH_RADIUS_M)
        exec(block_code,ctx)
        return ctx['track_span']
    def slow(points):
        return max(em._distance(points[i],points[j]) for i in range(len(points)) for j in range(i+1,len(points)))
    for w in [30,120,240]:
        errors=[]
        payload=synth(5,w,'separated',20261023)
        for track in payload['uavs_coords_str'].values():
            pts=list(zip(track['lngs'],track['lats']))
            errors.append(abs(fast(pts)-slow(pts)))
        a,_=timed(lambda:slow(pts),10)
        b,_=timed(lambda:fast(pts),30)
        results['span'].append(dict(window=w,legacy=a,vectorized=b,speedup=a['medianMs']/b['medianMs'],
                                   comparedTracks=5,maxAbsErrorMeters=max(errors)))
    for layout in ['separated','dense']:
        for n in [10,50,100,200]:
            objs=adapter._prepare_tracks(synth(n,120,layout,20261023)['uavs_coords_str'])['objects']
            stats,split=timed(lambda:SplitClusters(objs),20)
            results['dbscan'].append(dict(n=n,layout=layout,window=120,timing=stats,
                                         groupCount=len(set(split.last_clustering().tolist()))))
    return results


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=ROOT/'simulation_benchmark_20261023')
    parser.add_argument('--iterations',type=int,default=8,help='per independent seed; 3 seeds')
    parser.add_argument('--smoke',action='store_true')
    args=parser.parse_args()
    out=args.output.resolve(); out.mkdir(parents=True,exist_ok=True)
    (out/'inputs').mkdir(exist_ok=True)
    data=dict(timestampUTC=datetime.now(timezone.utc).isoformat(),seedList=[20261023,20261024,20261025],
        python=sys.version,platform=platform.platform(),processor=platform.processor(),logicalCpus=os.cpu_count(),
        torchVersion=torch.__version__,numpyVersion=np.__version__,torchThreads=torch.get_num_threads(),
        device='cpu',vectorizedFeatures=True,iterationsPerSeed=args.iterations,warmupPerSeed=2,
        percentileDefinition='nearest rank: sorted[ceil(0.95*n)-1]',api=[],
        sourceHashes={str(p.relative_to(PROJECT)):sha(p) for p in [Path(__file__),PROJECT/'situation_judgment/engine.py',
                    PROJECT/'situation_judgment/legacy_adapter.py',PROJECT/'situation_judgment/vectorized_features.py',
                    PROJECT/'formation_recognition/clusters_recognition.py',PROJECT/'config.ini',
                    PROJECT/'pretrained_weights/formation_recognition/form_recog_model_20260812_200622.pth']})
    log=(out/'execution.log').open('w',encoding='utf-8')
    app=Flask(__name__)
    with contextlib.redirect_stdout(log),contextlib.redirect_stderr(log):
        engine=register_situation_routes(app)
        start=time.perf_counter(); data['warmupReport']=engine.warmup()
        data['warmupMs']=(time.perf_counter()-start)*1000
    client=app.test_client()
    cases=[(n,w,layout) for layout in ['separated','dense'] for w in [30,120,240] for n in [10,50,100,200]]
    if args.smoke: cases=[(10,30,'separated')]
    for n,w,layout in cases:
        samples=[]; stages={}; groups=[]; codes=[]; raw=[]; diagnostics=[]
        with RssSampler() as rss:
            for seed in data['seedList']:
                payload=synth(n,w,layout,seed)
                path=out/'inputs'/f'{layout}_n{n}_w{w}_seed{seed}.json'
                path.write_text(json.dumps(payload,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
                for rep in range(2+args.iterations):
                    request=deepcopy(payload)
                    request['requestId']=f'sim-{layout}-{n}-{w}-{seed}-{rep}'
                    with contextlib.redirect_stdout(log),contextlib.redirect_stderr(log):
                        start=time.perf_counter()
                        response=client.post('/api/v1/situation/analyze',json=request)
                        elapsed=(time.perf_counter()-start)*1000
                    body=response.get_json()
                    if response.status_code!=200 or body.get('code')!=0:
                        raise RuntimeError(f'bad response {response.status_code} {body}')
                    if rep<2: continue
                    samples.append(elapsed); codes.append(body['code'])
                    timings=body.get('diagnostics',{}).get('performanceTimings',{})
                    for key,value in timings.items():
                        if isinstance(value,(int,float)): stages.setdefault(key,[]).append(value*1000)
                    raw.append(dict(seed=seed,iteration=rep-2,routeMs=elapsed,reportedSeconds=timings))
                    info=body.get('data',{})
                    if info.get('skippedTargets') or info.get('exemptTargetResults'):
                        raise RuntimeError('Synthetic targets unexpectedly skipped or exempted: '+str(info.get('skippedTargets')))
                    if len(info.get('targetIntentResults',[])) != n:
                        raise RuntimeError('Not all synthetic targets reached intent analysis')
                    prep=info.get('algorithmDiagnostics',{}).get('trajectoryPreprocessing',{})
                    if prep.get('inputTargetCount') != n or prep.get('outputTargetCount') != n:
                        raise RuntimeError('Not all synthetic targets reached legacy adapter: '+str(prep))
                    groups.append(info.get('analysisResult',{}).get('clusterCount'))
                    diagnostics.append(info.get('algorithmDiagnostics',{}))
            row=dict(n=n,window=w,layout=layout,totalInputPoints=n*w,route=summary(samples),
                     stages={k:summary(v) for k,v in stages.items()},codesAllZero=all(x==0 for x in codes),
                     groupCounts=groups,algorithmDiagnostics=diagnostics[-1],rss=rss.report(),samples=raw)
        row['rss']=rss.report()
        data['api'].append(row)
        (out/'results.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
        print(f'API {layout} N={n} W={w} median={row["route"]["medianMs"]:.2f}ms p95={row["route"]["p95Ms"]:.2f}ms',flush=True)
    if not args.smoke:
        print('Starting component A/B and consistency measurements',flush=True)
        with contextlib.redirect_stdout(log),contextlib.redirect_stderr(log):
            data['components']=components(out,log)
        # Request-local feature cache A/B; fresh IDs bypass whole-request idempotency.
        data['cacheComparison']=[]
        for layout in ['separated','dense']:
            payload=synth(100,120,layout,20261023)
            samples=[[],[]]; returned=[None,None]; calls=[0,0]
            original=em.SituationEngine._member_intent_features
            compute=em.SituationEngine._compute_member_intent_features
            mode=0
            def wrapper(self,target,params,spatial_context=None,feature_cache=None):
                return original(self,target,params,spatial_context,feature_cache if mode==0 else None)
            def counted(self,*a,**kw):
                calls[mode]+=1
                return compute(self,*a,**kw)
            with patch.object(em.SituationEngine,'_member_intent_features',new=wrapper), patch.object(em.SituationEngine,'_compute_member_intent_features',new=counted):
                for rep in range(17):
                    for mode in ([0,1] if rep%2==0 else [1,0]):
                        request=deepcopy(payload); request['requestId']=f'cache-{layout}-{rep}-{mode}'
                        with contextlib.redirect_stdout(log),contextlib.redirect_stderr(log):
                            start=time.perf_counter(); response=client.post('/api/v1/situation/analyze',json=request)
                            elapsed=(time.perf_counter()-start)*1000
                        body=response.get_json()
                        if response.status_code!=200 or body.get('code')!=0: raise RuntimeError(body)
                        returned[mode]=body.get('data',{})
                        if rep>=2: samples[mode].append(elapsed)
            # Timing fields are outside data; data can still contain request IDs.
            def clean(value):
                if isinstance(value,dict): return {k:clean(v) for k,v in value.items() if k not in ['requestId','performanceTimings']}
                if isinstance(value,list): return [clean(v) for v in value]
                return value
            data['cacheComparison'].append(dict(n=100,window=120,layout=layout,enabled=summary(samples[0]),
                disabled=summary(samples[1]),featureComputeCallsIncludingWarmup=calls,requestsPerMode=17,
                sameDataIgnoringRequestIdAndTimings=clean(returned[0])==clean(returned[1]),
                speedup=statistics.median(samples[1])/statistics.median(samples[0])))
    log.close()
    data['finishedUTC']=datetime.now(timezone.utc).isoformat()
    (out/'results.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    print('DONE '+str(out/'results.json'),flush=True)


if __name__=='__main__':
    main()
