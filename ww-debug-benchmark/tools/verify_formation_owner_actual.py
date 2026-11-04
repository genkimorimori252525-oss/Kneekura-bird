#!/usr/bin/env python3
"""Compare saved private-candidate and actual-source stand-in records."""
import argparse,hashlib,json,pathlib,shutil,subprocess,sys

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate',type=pathlib.Path,required=True)
    parser.add_argument('--actual',type=pathlib.Path,required=True)
    parser.add_argument('--output',type=pathlib.Path,required=True)
    a=parser.parse_args();out=a.output.absolute();out.mkdir(mode=0o700)
    dirs={'candidate':a.candidate.resolve(),'actual':a.actual.resolve()}
    reports={k:json.loads((p/'report.json').read_text()) for k,p in dirs.items()}
    errors=[];records={};inputs=[];historical_checks=[]
    repository=pathlib.Path(__file__).resolve().parents[2]
    git=pathlib.Path(shutil.which('git')).resolve()
    def check(ok,msg):
        if not ok:errors.append(msg)
    for mode,p in dirs.items():
        r=reports[mode];check(r['mode']==mode,mode+' mode');check(r['inputs_unchanged'] and r['classpath_unchanged'],mode+' source/classpath changed')
        for key,value in list(r['inputs_before'].items())+list(r['classpath_before'].items())+list(r['compiled_classes'].items()):
            f=pathlib.Path(key)
            if mode=='candidate' and f==repository/'ww-debug-benchmark/tools/observe_formation_owner_candidate.py':
                snapshot=p/'runner-snapshot.py';inputs.append(snapshot);check(sha(snapshot)==value,'candidate saved runner hash');continue
            old_sources={repository/'ww-debug-benchmark/src/main/java/com/wwdebug/autopilot/ControlAuthorityArbiter.java',repository/'ww-debug-benchmark/src/main/java/com/wwdebug/autopilot/FormationFlightManager.java'}
            if mode=='candidate' and f in old_sources:
                rel=f.relative_to(repository).as_posix();argv=[str(git),'show','e3fe81aed8884eeb1e9a71f6d42e557aed2ce58c:'+rel]
                rblob=subprocess.run(argv,cwd=repository,capture_output=True);blob_sha=hashlib.sha256(rblob.stdout).hexdigest()
                historical_checks.append({'argv':argv,'exit':rblob.returncode,'sha256':blob_sha,'expected':value})
                check(rblob.returncode==0 and blob_sha==value,mode+' historical git blob '+rel);continue
            inputs.append(f);check(f.is_file() and sha(f)==value,mode+' hash '+key)
        inputs.append(p/'runner-snapshot.py');check(sha(p/'runner-snapshot.py')==r['runner_snapshot_sha256'],mode+' runner snapshot')
    actual=reports['actual'];check(actual['actual_provenance'] and actual['source_copy_equal'] and not actual['patch_files'],'actual provenance')
    check(reports['candidate']['classpath_before']==actual['classpath_before'],'classpath differs')
    for rel in sorted(p.relative_to(dirs['candidate']/'source-copy') for p in (dirs['candidate']/'source-copy').rglob('*.java')):
        old=dirs['candidate']/'source-copy'/rel;new=dirs['actual']/'source-copy'/rel;inputs.extend((old,new))
        check(new.is_file() and sha(old)==sha(new),'source bytes differ '+str(rel))
    for rel in sorted(p.relative_to(dirs['candidate']/'stubs') for p in (dirs['candidate']/'stubs').rglob('*.java')):
        old=dirs['candidate']/'stubs'/rel;new=dirs['actual']/'stubs'/rel;inputs.extend((old,new))
        check(new.is_file() and sha(old)==sha(new),'fixture bytes differ '+str(rel))
    candidate_runs=reports['candidate']['runs'];actual_runs=actual['runs'];check(set(candidate_runs)==set(actual_runs),'case names differ')
    def filter_warning(text):
        return '\n'.join(s for s in text.splitlines() if 'WARN Advanced terminal features are not available in this environment' not in s)
    for case in sorted(set(candidate_runs)&set(actual_runs)):
        check(candidate_runs[case]['exit']==actual_runs[case]['exit'],case+' exit differs')
        if case=='compile':continue
        left=dirs['candidate']/(case+'.stdout');right=dirs['actual']/(case+'.stdout');inputs.extend((left,right))
        l,r=filter_warning(left.read_text()),filter_warning(right.read_text())
        check(l==r,case+' stdout differs after excluding only documented terminal warning')
        records[case]={'exit':actual_runs[case]['exit'],'candidate_stdout_sha256':sha(left),'actual_stdout_sha256':sha(right),'filtered_equal':l==r}
    script=pathlib.Path(__file__).resolve();inputs.extend((script,git,dirs['candidate']/'report.json',dirs['actual']/'report.json'))
    result={'scope':'Compare saved source-copy stand-in runs only; no runtime, MOD, native setter or safety claim. Candidate original source hashes are checked against local Git blobs and runner against its saved snapshot. One known terminal warning line is excluded from stdout comparisons. Combat swaps and artificial exceptions remain nonzero.','errors':errors,'historical_git_blob_checks':historical_checks,'cases':records,'input_sha256':{str(p):sha(p) for p in dict.fromkeys(inputs) if p.is_file()},'verifier_sha256':sha(script)}
    (out/'report.json').write_text(json.dumps(result,indent=2)+'\n');print('errors',len(errors));return 1 if errors else 0
if __name__=='__main__':sys.exit(main())
