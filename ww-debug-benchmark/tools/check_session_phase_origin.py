#!/usr/bin/env python3
"""Compare selected fake-session outcomes and trace points; not a flight verdict."""
import argparse
import json
from pathlib import Path
import sys

CASES=['unchanged','heading','turntimeout','missiontimeout','prestall','postterrain',
       'eventexception','frameexception']
EXPECTED={
 'unchanged':'entry=TURN_RIGHT dispatch=TURN_RIGHT afterPlan=TURN_RIGHT terminal=false emergency=false exit=TURN_RIGHT',
 'heading':'entry=TURN_RIGHT dispatch=TURN_RIGHT afterPlan=STALL_SETUP terminal=false emergency=false exit=STALL_SETUP',
 'turntimeout':'entry=TURN_RIGHT dispatch=TURN_RIGHT afterPlan=ABORTED terminal=false emergency=false exit=ABORTED',
 'missiontimeout':'entry=TURN_RIGHT dispatch=null afterPlan=null terminal=true emergency=false exit=ABORTED',
 'prestall':'entry=TURN_RIGHT dispatch=STALL_RECOVERY afterPlan=STALL_RECOVERY terminal=false emergency=false exit=STALL_RECOVERY',
 'postterrain':'entry=TURN_RIGHT dispatch=TURN_RIGHT afterPlan=TURN_RIGHT terminal=false emergency=true exit=TURN_RIGHT',
 'eventexception':'entry=TURN_RIGHT dispatch=TURN_RIGHT afterPlan=null terminal=false emergency=false exit=null',
 'frameexception':'entry=TURN_RIGHT dispatch=TURN_RIGHT afterPlan=TURN_RIGHT terminal=false emergency=false exit=null',
}
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('observation',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    root=a.observation.resolve(strict=True); report=json.loads((root/'report.json').read_text(encoding='utf-8')); checks=[]
    def check(name,passed,detail):checks.append({'name':name,'pass':bool(passed),'detail':detail})
    def get(mode,case):
        lines=(root/mode/(case+'.stdout')).read_text(encoding='utf-8').splitlines();result={}
        for prefix in ('CASE','STATE','OUTPUT','LAST','EVENTS','FRAMES','THROWN'):
            matches=[x[len(prefix)+1:] for x in lines if x.startswith(prefix+' ')]
            if len(matches)!=1:raise ValueError(mode+'/'+case+' missing or duplicate '+prefix)
            result[prefix]=matches[0]
        trace=[x[6:] for x in lines if x.startswith('TRACE ')]
        if mode=='traced' and len(trace)!=1:raise ValueError(mode+'/'+case+' missing or duplicate trace')
        if mode=='baseline' and trace:raise ValueError('baseline unexpectedly traced')
        return result,trace[0] if trace else None
    for key in ('source_unchanged','runner_unchanged','fixture_unchanged','dependencies_unchanged'):
        check(key,report.get(key) is True,report.get(key))
    check('all child exits',len(report['runs'])==18 and all(x['exit']==0 for x in report['runs'].values()),len(report['runs']))
    for mode in ('baseline','traced'):
        lines=(root/mode/'heading.classes.log').read_text(encoding='utf-8').splitlines()
        for name in ('AutopilotSession','FlightProfile','FlightPhase','FlightControlOutput'):
            matches=[x for x in lines if 'com.wwdebug.autopilot.'+name+' source:' in x]
            expected='file:'+str(root/mode/'classes')+'/'
            check(mode+' load '+name,len(matches)==1 and expected in matches[0],matches)
    for case in CASES:
        baseline,_=get('baseline',case);traced,trace=get('traced',case)
        check(case+' unchanged selected output and logs',baseline==traced,{'baseline':baseline,'traced':traced})
        check(case+' expected trace',trace.startswith(EXPECTED[case]),trace)
        if case.endswith('exception'):
            check(case+' injected same sentinel','fixture-sentinel:same=true' in traced['THROWN'] and traced['OUTPUT']=='null' and traced['LAST']=='null',traced)
        else:
            check(case+' returned object agrees',traced['THROWN']=='none' and ' returned='+traced['OUTPUT'] in trace,traced)
    result={'checks':checks,'failed':[c for c in checks if not c['pass']],
      'limits':['fake snapshot/world/logger; direct session tick only, not a native setter or control-selection result',
                'trace calls alter the private source copy; no full runtime or Mixin compatibility proof',
                'first plan-dispatch phase differs from tick-entry after guards, and plan can transition before returning',
                'returned session output can be replaced later by route, terrain or adaptation',
                'exceptions are artificial logger sentinels, not proven real logger failure semantics',
                'class origin sampled for one case; hashes are snapshots, no complete integrity or provenance guarantee']}
    with a.output.open('x',encoding='utf-8') as stream:json.dump(result,stream,indent=2);stream.write('\n')
    print('checks',len(checks),'failures',len(result['failed']),flush=True)
    return 1 if result['failed'] else 0
if __name__=='__main__':sys.exit(main())
