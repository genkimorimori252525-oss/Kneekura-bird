#!/usr/bin/env python3
"""Verify saved synthetic source-copy results; not an actual MOD safety test."""
import argparse, hashlib, json, pathlib, sys

def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def line(p, prefix):
    matches=[s for s in p.read_text().splitlines() if s.startswith(prefix)]
    if len(matches)!=1: raise ValueError(f'{p}: expected one {prefix!r}, found {len(matches)}')
    return matches[0]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline',type=pathlib.Path,required=True)
    parser.add_argument('--candidate',type=pathlib.Path,required=True)
    parser.add_argument('--descriptor',type=pathlib.Path,required=True)
    parser.add_argument('--output',type=pathlib.Path,required=True)
    args=parser.parse_args();out=args.output.absolute();out.mkdir(mode=0o700)
    sources={'baseline':args.baseline.resolve(),'candidate':args.candidate.resolve()}
    reports={k:json.loads((v/'report.json').read_text()) for k,v in sources.items()}
    errors=[]; observations={}; consumed=[]
    def check(ok,msg):
        if not ok: errors.append(msg)
    for mode,p in sources.items():
        r=reports[mode];check(r['mode']==mode,mode+' mode');check(r['inputs_unchanged'] and r['classpath_unchanged'],mode+' recorded hashes changed')
        for key,expected in r['inputs_before'].items():
            target=pathlib.Path(key);consumed.append(target)
            check(target.is_file() and digest(target)==expected, mode+' input mismatch '+key)
        for key,expected in r['classpath_before'].items():
            target=pathlib.Path(key);consumed.append(target)
            check(target.is_file() and digest(target)==expected,mode+' classpath mismatch '+key)
        for key,expected in r['compiled_classes'].items():
            target=pathlib.Path(key);consumed.append(target)
            check(target.is_file() and digest(target)==expected,mode+' class mismatch '+key)
        check(digest(p/'runner-snapshot.py')==r['runner_snapshot_sha256'],mode+' runner snapshot')
        check(len(r['runs'])==48,mode+' run count')
        expected_red={'formation-swap','formation-same-uuid','combat-swap','combat-same-uuid'} if mode=='baseline' else {'combat-swap','combat-same-uuid'}
        deliberate={k for k in r['runs'] if k.startswith(('inject-', 'combat-inject-'))}
        if mode=='baseline': deliberate.add('pending-level-callback')
        for name,result in r['runs'].items():
            want=42 if name in expected_red or name in deliberate else 0
            check(result['exit']==want,f'{mode} {name}: exit {result["exit"]}, expected {want}')
            stdout=p/(name+'.stdout');stderr=p/(name+'.stderr');consumed.extend((stdout,stderr))
            if name.startswith(('inject-', 'combat-inject-')):
                want_identity='uncaught_runtime_identity=true uncaught_error_identity=false' if name.endswith('-runtime') else 'uncaught_runtime_identity=false uncaught_error_identity=true'
                check(want_identity in stdout.read_text(),f'{mode} {name}: sentinel identity')
                check('getter_trace=' in stdout.read_text(),f'{mode} {name}: trace missing')
        check(line(p/'wrapper-empty.stdout','wrapper_outcome=')=='wrapper_outcome=NONE getter_trace=[level:formation, level:formation, pilot:pilotOf-formation]',mode+' empty wrapper order')
        check('removed_result=false getter_trace=[]' in (p/'removed-short-circuit.stdout').read_text(),mode+' removed short circuit')
        if mode=='candidate':
            check('formation_removed_result=false getter_trace=[]' in (p/'removed-short-circuit.stdout').read_text(),mode+' formation removed short circuit')
    comparable=['formation-same','combat-same','collision','risk-only','direct','claimed','formation-player','formation-empty','formation-client','formation-removed','combat-player','combat-empty','combat-client','combat-removed','formation-terrain','wrapper-empty','wrapper-populated']
    for case in comparable:
        def gettrace(p):
            raw=(p/(case+'.stdout')).read_text().splitlines()
            values=[s[s.index('getter_trace='):] for s in raw if 'getter_trace=' in s]
            if len(values)!=1:raise ValueError(f'{p}/{case}: trace count {len(values)}')
            return values[0]
        left,right=(gettrace(sources[m]) for m in ('baseline','candidate'))
        check(left==right,case+' getter trace changed');observations[case]=left
    for mode in ('baseline','candidate'):
        raw=(sources[mode]/'pending-level-callback.stdout').read_text()
        check('synthetic-getter-callback-swap' in raw,mode+' callback not reached')
        check('pilot_is_B=true' in raw,mode+' callback pilot not B')
        if mode=='baseline':check('writer_second_is_B=true' in raw,mode+' B write not observed')
        else:check('writer_second_is_B=false' in raw and 'authority=NONE' in raw and 'classification=CALLBACK_CONTRACT_GREEN' in raw,mode+' did not deny')
    descriptor=json.loads((args.descriptor/'report.json').read_text());consumed.append(args.descriptor/'report.json')
    signature='descriptor: (Lnet/minecraft/world/entity/Entity;)Lcom/wwdebug/autopilot/ControlOutcome;'
    javap=pathlib.Path(descriptor['javap']);consumed.append(javap)
    check(javap.is_file() and digest(javap)==descriptor['javap_sha256']==descriptor['javap_sha256_after'],'javap hash')
    for mode in ('baseline','candidate'):
        meta=descriptor['runs'][mode];stdout=args.descriptor/(mode+'.stdout');stderr=args.descriptor/(mode+'.stderr');text=stdout.read_text();consumed.extend((stdout,stderr))
        check(meta['exit']==0 and meta['class_before']==meta['class_after'],mode+' javap provenance')
        cls=pathlib.Path(meta['argv'][-1]);consumed.append(cls)
        check(meta['argv'][0]==str(javap) and cls.is_file() and digest(cls)==meta['class_before'],mode+' javap class')
        check(digest(stdout)==meta['stdout_sha256'] and digest(stderr)==meta['stderr_sha256'],mode+' javap output')
        check(text.count(signature)==1,mode+' public descriptor')
    summary={'scope':'Saved stand-in traces only. Getter callbacks, terrain, collision, control effects and runtime ownership are not proven. Combat swaps remain red; ABA/reentry are observational.', 'errors':errors,'comparable_trace_count':len(comparable),'observations':observations,'inputs_sha256':{str(x):digest(x) for x in dict.fromkeys(consumed) if x.is_file()},'verifier_sha256':digest(pathlib.Path(__file__).resolve())}
    (out/'report.json').write_text(json.dumps(summary,indent=2)+'\n');print('errors',len(errors));return 1 if errors else 0
if __name__=='__main__':sys.exit(main())
