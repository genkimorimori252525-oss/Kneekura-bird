#!/usr/bin/env python3
"""Check selected fake-session comparisons after a prior tick, not real runtime safety."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

CASES=('success','eventexception','frameexception')
PREFIXES=('PRIOR','CASE','STATE','OUTPUT','LAST','IDENTITY','EVENTS','FRAMES','THROWN')
EXPECTED={
 'success':('phase=TURN_RIGHT phaseTicks=102 missionTicks=1002','lastIsPrior=false lastIsResult=true',
            'entry=TURN_RIGHT dispatch=TURN_RIGHT afterPlan=TURN_RIGHT terminal=false emergency=false exit=TURN_RIGHT'),
 'eventexception':('phase=STALL_SETUP phaseTicks=0 missionTicks=1002','lastIsPrior=true lastIsResult=false',
                   'entry=TURN_RIGHT dispatch=TURN_RIGHT afterPlan=null terminal=false emergency=false exit=null'),
 'frameexception':('phase=TURN_RIGHT phaseTicks=102 missionTicks=1002','lastIsPrior=true lastIsResult=false',
                   'entry=TURN_RIGHT dispatch=TURN_RIGHT afterPlan=TURN_RIGHT terminal=false emergency=false exit=null')}

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('observation',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    root=a.observation.resolve(strict=True);report=json.loads((root/'report.json').read_text(encoding='utf-8'))
    wrapper=json.loads((root/'prior-wrapper-manifest.json').read_text(encoding='utf-8'));checks=[]
    def check(name,passed,detail):checks.append({'name':name,'pass':bool(passed),'detail':detail})
    def get(mode,case):
        lines=(root/mode/(case+'.stdout')).read_text(encoding='utf-8').splitlines();result={}
        for prefix in PREFIXES:
            matches=[x[len(prefix)+1:] for x in lines if x.startswith(prefix+' ')]
            if len(matches)!=1:raise ValueError(mode+'/'+case+' missing or duplicate '+prefix)
            result[prefix]=matches[0]
        traces=[x[6:] for x in lines if x.startswith('TRACE ')]
        if (mode=='traced' and len(traces)!=1) or (mode=='baseline' and traces):raise ValueError('trace count')
        return result,traces[0] if traces else None
    for key in ('source_unchanged','runner_unchanged','fixture_unchanged','dependencies_unchanged'):
        check(key,report.get(key) is True,report.get(key))
    check('wrapper before/after/snapshot',wrapper['wrapper_before']==wrapper['wrapper_after']==wrapper['wrapper_snapshot_sha256']==sha(root/'prior-runner-snapshot.py'),wrapper)
    check('base runner before/after/snapshot',wrapper['base_runner_before']==wrapper['base_runner_after']==sha(root/'runner-snapshot.py'),wrapper)
    check('base report hash',wrapper['base_report_sha256']==sha(root/'report.json'),wrapper['base_report_sha256'])
    check('all child exits',wrapper['base_exit']==0 and len(report['runs'])==8 and all(x['exit']==0 for x in report['runs'].values()),len(report['runs']))
    for mode in ('baseline','traced'):
        lines=(root/mode/'success.classes.log').read_text(encoding='utf-8').splitlines()
        for name in ('AutopilotSession','FlightProfile','FlightPhase','FlightControlOutput'):
            matches=[x for x in lines if 'com.wwdebug.autopilot.'+name+' source:' in x]
            path='file:'+str(root/mode/'classes')+'/'
            check(mode+' load '+name,len(matches)==1 and path in matches[0],matches)
    for case in CASES:
        baseline,_=get('baseline',case);traced,trace=get('traced',case);phase,identity,trace_prefix=EXPECTED[case]
        check(case+' selected state/output/frame/events match',baseline==traced,{'baseline':baseline,'traced':traced})
        check(case+' prior established','phase=TURN_RIGHT phaseTicks=101 missionTicks=1001' in traced['PRIOR'],traced['PRIOR'])
        check(case+' expected state and reference',phase in traced['STATE'] and traced['IDENTITY']==identity,[traced['STATE'],traced['IDENTITY']])
        check(case+' expected trace position',trace.startswith(trace_prefix),trace)
        if case=='success':
            check(case+' output and last agree',traced['THROWN']=='none' and traced['OUTPUT']==traced['LAST'] and traced['OUTPUT']!='null',traced)
        else:
            prior=traced['PRIOR'].split(' output=',1)[1]
            check(case+' same fake sentinel and stale prior',traced['OUTPUT']=='null' and traced['LAST']==prior and 'fixture-sentinel:same=true' in traced['THROWN'],traced)
    result={'checks':checks,'failed':[c for c in checks if not c['pass']],
      'limits':['two direct ticks with fake snapshot/world/logger; actual logger exceptions may differ',
                'prior output retained in synthetic exceptions, not a native setter or input-safety result',
                'observer fake reset is not session state and reentry is not exercised',
                'selected output fields and frame/event strings only; not complete side-effect equivalence',
                'class origins sampled for success case only; hash samples do not prove uninterrupted integrity',
                'actual Mixin/route/world/player/collision/terrain behavior remains untested']}
    with a.output.open('x',encoding='utf-8') as f:json.dump(result,f,indent=2);f.write('\n')
    print('checks',len(checks),'failures',len(result['failed']),flush=True)
    return 1 if result['failed'] else 0
if __name__=='__main__':sys.exit(main())
