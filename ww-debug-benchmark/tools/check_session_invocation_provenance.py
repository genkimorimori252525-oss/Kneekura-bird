#!/usr/bin/env python3
"""Check synthetic identity cases against recorded outputs, not runtime safety."""
import argparse
import json
from pathlib import Path
import sys

CASES=('normal','heading','prestall','emergency','terminal','different','routecopy',
       'previous','exception','nested','nesteddirect','nestedforeign','foreigncall','closed','crossthread')
REDS={'normal','heading','prestall','emergency','terminal','different','routecopy','previous','closed'}
NESTED={'nested','nesteddirect','nestedforeign','foreigncall'}
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--baseline',type=Path,required=True)
    p.add_argument('--candidate',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    roots={'baseline':a.baseline.resolve(strict=True),'candidate':a.candidate.resolve(strict=True)};checks=[]
    def check(name,passed,detail):checks.append({'name':name,'pass':bool(passed),'detail':detail})
    reports={k:json.loads((v/'report.json').read_text(encoding='utf-8')) for k,v in roots.items()}
    for mode,report in reports.items():
        check(mode+' report mode',report['mode']==mode,report['mode'])
        for key in ('source_unchanged','runner_unchanged','fixture_unchanged','dependencies_unchanged'):
            check(mode+' '+key,report.get(key) is True,report.get(key))
        check(mode+' complete child set',len(report['runs'])==len(CASES)+1 and report['runs']['compile']['exit']==0,len(report['runs']))
        for case in CASES:
            expected=1 if (mode=='baseline' and case in REDS) or (mode=='candidate' and case=='crossthread') else 0
            check(mode+' '+case+' exit',report['runs'][case]['exit']==expected,report['runs'][case]['exit'])
            if expected and mode=='baseline':
                stderr=(roots[mode]/(case+'.stderr')).read_text(encoding='utf-8')
                check(mode+' '+case+' expected assertion','AssertionError: same call required; other, previous, equal copy unknown' in stderr,stderr)
            if expected and mode=='candidate':
                stderr=(roots[mode]/(case+'.stderr')).read_text(encoding='utf-8')
                check('candidate cross-thread expected red','AssertionError: cross-thread session interleaving must be unknown' in stderr,stderr)
        lines=(roots[mode]/'normal.classes.log').read_text(encoding='utf-8').splitlines()
        for name in ('AutopilotSession','FlightProfile','FlightPhase','FlightControlOutput'):
            matches=[x for x in lines if 'com.wwdebug.autopilot.'+name+' source:' in x]
            check(mode+' origin '+name,len(matches)==1 and ('file:'+str(roots[mode]/'classes')+'/') in matches[0],matches)
    for case in CASES:
        def get(mode):
            lines=(roots[mode]/(case+'.stdout')).read_text(encoding='utf-8').splitlines(); result={}
            for prefix in ('CASE','ORIGIN','RESULT','VALUES','EVENTS','FRAMES','CLOSED'):
                matches=[x[len(prefix)+1:] for x in lines if x.startswith(prefix+' ')]
                if len(matches)!=1:raise ValueError(mode+'/'+case+' missing or duplicate '+prefix)
                result[prefix]=matches[0]
            return result
        b,c=get('baseline'),get('candidate')
        # ORIGIN and CASE differ intentionally; compare only non-instrumentation observations.
        keys=('RESULT','VALUES','EVENTS','FRAMES','CLOSED')
        check(case+' selected original outcome unchanged',all(b[k]==c[k] for k in keys),{'baseline':{k:b[k] for k in keys},'candidate':{k:c[k] for k in keys}})
        expected_same='same=false' if case in NESTED or case=='exception' else 'same=true'
        check(case+' candidate scoped disposition',expected_same in c['CASE'] and 'other=false' in c['CASE'] and 'previous=false' in c['CASE'] and 'copy=false' in c['CASE'] and c['CLOSED']=='false',c['CASE'])
        if case in NESTED:
            check(case+' invalidated nested or foreign', 'frameInvalid=true' in c['CASE'],c['CASE'])
        if case=='routecopy':check('equal-valued replacement is unknown','valueEqual=true' in c['CASE'] and 'copy=false' in c['CASE'],c['CASE'])
        if case=='previous':check('previous value is unknown','previous=false' in c['CASE'] and 'valueEqual=true' in c['CASE'],c['CASE'])
        if case=='exception':check('exception remains same synthetic sentinel','fixture-sentinel:same=true' in c['RESULT'] and 'same=false' in c['CASE'],c['RESULT'])
        if case=='crossthread':check('cross-thread false PRESENT observed','same=true' in c['CASE'] and 'frameInvalid=false' in c['CASE'],c['CASE'])
    result={'checks':checks,'failed':[c for c in checks if not c['pass']],
      'limits':['test-only source-copy plus fake scope, logger and snapshot; not used for flight control',
                'nested and other-session checks are synthetic same-thread cases; concurrent mutation and ABA unproved',
                'reference equality only detects some replacement; identical-reference transforms remain unknown',
                'no route Mixin, game runtime, real player, native setter or safety gate executed',
                'selected result/value/event/frame summaries and one-case class origins; no full equivalence',
                'input and JDK hashes are samples, not authentication or uninterrupted integrity']}
    with a.output.open('x',encoding='utf-8') as f:json.dump(result,f,indent=2);f.write('\n')
    print('checks',len(checks),'failures',len(result['failed']),flush=True)
    return 1 if result['failed'] else 0
if __name__=='__main__':sys.exit(main())
