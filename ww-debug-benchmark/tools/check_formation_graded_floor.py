#!/usr/bin/env python3
"""Check selected differences in a completed graded target-floor observation.

Assertions concern fake writes and declared fixture branches only. Non-finite
inputs, native setters, whole-flight safety and causation remain unqualified.
"""
import argparse
import json
import math
from pathlib import Path
import re
import sys

NAMES = ('ControlAuthorityArbiter', 'FormationFlightManager', 'AirspaceSafetyProbe',
         'MobPilotGate', 'ControlOutcome', 'ControlProposal', 'FlightControlOutput',
         'FlightPhase', 'AutopilotSession', 'FlightProfile', 'AutonomousFlightManager')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('observation',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    root=args.observation.resolve(strict=True)
    report=json.loads((root/'report.json').read_text(encoding='utf-8'))
    checks=[]
    def check(name,ok,detail):
        checks.append({'name':name,'pass':bool(ok),'detail':detail})
    def read(mode,case):
        lines=(root/mode/(case+'.stdout')).read_text(encoding='utf-8').splitlines()
        def one(prefix):
            matches=[x[len(prefix):] for x in lines if x.startswith(prefix)]
            if len(matches)!=1:raise ValueError(mode+'/'+case+': missing or duplicate '+prefix)
            return matches[0]
        raw=one('WRITES ')
        if not (raw.startswith('[') and raw.endswith(']')):raise ValueError(raw)
        chunks=raw[1:-1].split(', ') if raw!='[]' else []
        writes=[[float(x) for x in chunk.split(',')] for chunk in chunks]
        if any(len(x)!=4 for x in writes):raise ValueError('invalid write '+raw)
        return one('OBS '),writes,one('ADAPTERS '),one('RISK ')
    def eq(a,b):return math.isfinite(a) and math.isfinite(b) and abs(a-b)<1e-6
    for item in ('source_unchanged','runner_unchanged','fixture_unchanged','dependencies_unchanged'):
        check(item,report.get(item) is True,report.get(item))
    check('all child exits',len(report['runs'])==70 and all(x['exit']==0 for x in report['runs'].values()),len(report['runs']))
    # Selected grouped cases must load all named production classes from this stage.
    for mode in ('baseline','candidate'):
        log=(root/mode/'1549-low.classes.log').read_text(encoding='utf-8')
        expected=(root/mode/'classes').as_uri()+'/'
        for name in NAMES:
            matching=[line for line in log.splitlines() if 'com.wwdebug.autopilot.'+name+' source:' in line]
            # HotSpot spells local file URLs as file:/path; URI canonical identity is not proved.
            path_spelling='file:'+str(root/mode/'classes')+'/'
            check(mode+' load '+name,len(matching)==1 and path_spelling in matching[0],matching)
    for case,baseline_engine,candidate_engine in [('1549-low',.08,1.0),('1589-low',.9,1.0),('1549-below',.08,.42),('1549-equal',.08,.42),('1549-above',.08,.42)]:
        b=read('baseline',case);c=read('candidate',case)
        check(case+' reached same turn slot',all('auth=FORMATION phase=TURN_RIGHT' in x[0] for x in (b,c)) and len(b[1])==len(c[1])==2,[b[0],c[0]])
        if len(b[1])==len(c[1])==2:
            check(case+' baseline documented output',eq(b[1][1][3],baseline_engine),b[1])
            check(case+' candidate throttle',eq(c[1][1][3],candidate_engine),c[1])
            check(case+' same base and axes',all(eq(x,y) for x,y in zip(b[1][0],c[1][0])) and all(eq(x,y) for x,y in zip(b[1][1][:3],c[1][1][:3])),[b[1],c[1]])
            match=re.search(r'targetSpeed=([^:]+):targetAltitude=',c[2])
            check(case+' candidate reported target',bool(match) and eq(float(match.group(1)),34.644173364843915) and 'formation_turn_floor_target' in c[2],c[2])
    for case in ('1549-ungrouped','1549-leader',
                 '1549-terrain','1549-collision','1549-player','1549-missingprofile',
                 '1589-timeout','1589-riskonly','1589-heading'):
        b=read('baseline',case);c=read('candidate',case)
        check(case+' selected outcome unchanged',b==c,[b,c])
    # Late takeover retains an earlier base write; this is not a zero-player-write proof.
    for case,label in [('1549-playerlate','auth=PLAYER_CONTROLLED'),('1549-moblate','auth=NONE')]:
        b=read('baseline',case);c=read('candidate',case)
        check(case+' no pending call after replacement',label in b[0] and label in c[0] and len(b[1])==len(c[1])==1 and b[1]==c[1],[b[0],b[1],c[0],c[1]])
    b=read('baseline','1549-combat');c=read('candidate','1549-combat')
    check('combat claim suppresses pending setter','auth=DEFENSIVE_COMBAT' in b[0] and 'auth=DEFENSIVE_COMBAT' in c[0] and len(b[1])==len(c[1])==1 and b[1]==c[1],[b[0],c[0]])
    b=read('baseline','1549-fastleader');c=read('candidate','1549-fastleader')
    bm=re.search(r'targetSpeed=([^:]+):targetAltitude=',b[2]);cm=re.search(r'targetSpeed=([^:]+):targetAltitude=',c[2])
    check('higher leader target retained',len(b[1])==len(c[1])==2 and bm is not None and cm is not None and float(bm.group(1))>34.644173364843915 and eq(float(bm.group(1)),float(cm.group(1))) and b[1]==c[1] and b[2]==c[2],[b[0],b[1],b[2],c[0],c[1],c[2]])
    # These are single, independently constructed states, not a flight trajectory.
    steps={'err08minus':.42,'err08equal':.42,'err08plus':.76,
           'err35minus':.76,'err35equal':.76,'err35plus':1.0,
           'neg08minus':.24,'neg08equal':.42,'neg08plus':.42,
           'neg25minus':.08,'neg25equal':.24,'neg25plus':.24}
    for case,expected_engine in steps.items():
        b=read('baseline','1549-'+case);c=read('candidate','1549-'+case)
        match=re.search(r'targetSpeed=([^:]+):targetAltitude=',c[2])
        check(case+' candidate stepped engine',len(b[1])==len(c[1])==2 and eq(c[1][1][3],expected_engine)
              and all(eq(x,y) for x,y in zip(b[1][0],c[1][0]))
              and all(eq(x,y) for x,y in zip(b[1][1][:3],c[1][1][:3]))
              and match is not None and eq(float(match.group(1)),34.644173364843915),[b[1],c[1],c[2]])
    b=read('baseline','1589-heading');c=read('candidate','1589-heading')
    check('heading transition retains old base output','phase=STALL_SETUP' in b[0] and 'base=turn_speed_recovery' in b[0] and b==c,[b[0],c[0]])
    b=read('baseline','1589-riskonly');c=read('candidate','1589-riskonly')
    check('risk-only label has no collision writer','auth=COLLISION_AVOIDANCE phase=ABORTED' in b[0] and b[3]=='true' and len(b[1])==1 and b==c,[b[0],b[1],b[3]])
    nonfinite={case:{m:read(m,case) for m in ('baseline','candidate')} for case in ('1549-nanspeed','1549-infspeed','1549-nanleader')}
    result={'checks':checks,'failed':[x for x in checks if not x['pass']],
            'nonfinite_observations_NOT_SAFETY':nonfinite,
            'limits':['fake world/snapshot/logger/adapter; no actual flight or native setter',
                      '1549/1589 same-tick logs not necessarily simultaneous; #226 reconstruction differs from original',
                      'finite turn-floor boundary no longer switches in these samples; existing speed-error steps remain discontinuous',
                      'near-floor base recovery commands 1.0 but candidate pending slot commands 0.42; no recovery guarantee',
                      'no oscillation/acceleration/closure/collision safety result',
                      'heading transition retains base recovery but candidate does not apply',
                      'late player/mob cases retain earlier base write; no takeover safety result',
                      'fake snapshot reads live entity rather than immutable runtime record',
                      'selected class loads only; no continuous file integrity or Mixin transform proof',
                      'nonfinite input observations have no safety verdict']}
    # Exclusive output prevents a stale prior report being mistaken for this run.
    with args.output.open('x',encoding='utf-8') as stream:json.dump(result,stream,indent=2,allow_nan=False);stream.write('\n')
    print('checks',len(checks),'failures',len(result['failed']),'nonfinite cases observational',flush=True)
    return 1 if result['failed'] else 0

if __name__=='__main__':sys.exit(main())
