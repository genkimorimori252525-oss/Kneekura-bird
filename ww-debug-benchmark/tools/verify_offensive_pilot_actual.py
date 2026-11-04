#!/usr/bin/env python3
"""Compare saved private-candidate and actual-source offensive stand-in records."""
import argparse,hashlib,json,pathlib,shutil,subprocess,sys,urllib.parse

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--candidate',type=pathlib.Path,required=True);p.add_argument('--actual',type=pathlib.Path,required=True);p.add_argument('--output',type=pathlib.Path,required=True);a=p.parse_args();out=a.output.absolute();out.mkdir(mode=0o700);dirs={'candidate':a.candidate.resolve(),'actual':a.actual.resolve()};reports={k:json.loads((v/'report.json').read_text()) for k,v in dirs.items()};repository=pathlib.Path(__file__).resolve().parents[2];git=pathlib.Path(shutil.which('git')).resolve();errors=[];inputs=[];history=[];cases={}
 def check(ok,msg):
  if not ok:errors.append(msg)
 old={repository/'ww-debug-benchmark/src/main/java/com/wwdebug/autopilot'/n for n in ('AirCombatManeuverManager.java','FighterCombatFacade.java','ControlAuthorityArbiter.java')};old_runner=repository/'ww-debug-benchmark/tools/observe_offensive_pilot_candidate.py'
 for mode,root in dirs.items():
  r=reports[mode];check(r['mode']==mode,mode+' mode');check(r['inputs_unchanged'] and r['classpath_unchanged'] and r['stage_stable'],mode+' stability');check(sha(root/'runner-snapshot.py')==r['runner_snapshot_sha256'],mode+' runner snapshot');inputs.extend((root/'runner-snapshot.py',root/'report.json'))
  for name,value in list(r['inputs_before'].items())+list(r['classpath_before'].items())+list(r['compiled_classes'].items()):
   f=pathlib.Path(name)
   if mode=='candidate' and f==old_runner:check(sha(root/'runner-snapshot.py')==value,'historical runner');continue
   if mode=='candidate' and f in old:
    rel=f.relative_to(repository).as_posix();argv=[str(git),'show','d34594f:'+rel];result=subprocess.run(argv,cwd=repository,capture_output=True);h=hashlib.sha256(result.stdout).hexdigest();history.append({'argv':argv,'exit':result.returncode,'sha256':h,'expected':value});check(result.returncode==0 and h==value,'historical source '+rel);continue
   inputs.append(f);check(f.is_file() and sha(f)==value,mode+' input '+name)
  for name,entry in r['runs'].items():
   for path,value in entry['outputs_immediate'].items():
    f=pathlib.Path(path);inputs.append(f);check(f.is_file() and sha(f)==value,mode+' output '+path)
   if name!='compile':check(entry['classes_before']==entry['classes_after']==r['compiled_classes'],mode+' staged classes changed '+name)
 actual=reports['actual'];check(actual['source_copy_equal'] and not actual['patch_files'],'actual copy or patch');check(all(actual['source_hashes'][k]==v for k,v in actual['expected_source_hashes'].items()),'actual expected sources');check(reports['candidate']['classpath_before']==actual['classpath_before'],'classpath differs');check(reports['candidate']['fixture_sha256']==actual['fixture_sha256'],'fixture source differs')
 for sub in ('source-copy','stubs'):
  left=dirs['candidate']/sub;right=dirs['actual']/sub;ls=sorted(x.relative_to(left) for x in left.rglob('*.java'));rs=sorted(x.relative_to(right) for x in right.rglob('*.java'));check(ls==rs,sub+' file set differs')
  for rel in ls:
   x,y=left/rel,right/rel;inputs.extend((x,y));check(y.is_file() and sha(x)==sha(y),sub+' bytes '+str(rel))
 before=reports['candidate']['runs'];after=actual['runs'];check(set(before)==set(after),'case names differ');check(len(before)==37,'case count')
 def clean(text):return '\n'.join(s for s in text.splitlines() if 'WARN Advanced terminal features are not available in this environment' not in s)
 for name in sorted(set(before)&set(after)):
  check(before[name]['exit']==after[name]['exit'],name+' exit differs')
  if name=='compile':continue
  x=dirs['candidate']/(name+'.stdout');y=dirs['actual']/(name+'.stdout');same=clean(x.read_text())==clean(y.read_text());check(same,name+' stdout differs');cases[name]={'candidate_exit':before[name]['exit'],'actual_exit':after[name]['exit'],'candidate_stdout_sha256':sha(x),'actual_stdout_sha256':sha(y),'equal_except_terminal_warning':same}
 script=pathlib.Path(__file__).resolve();inputs.extend((script,git));result={'scope':'Comparison of saved copied-source fake fixtures only. Historical original paths checked against local Git blobs, not authenticated externally. The known terminal-feature warning is excluded; actual MOD, firing, runtime, physical safety and native setter success are not proven.','errors':errors,'historical_git_blob_checks':history,'cases':cases,'input_sha256':{str(x):sha(x) for x in dict.fromkeys(inputs) if x.is_file()},'verifier_sha256':sha(script)};(out/'report.json').write_text(json.dumps(result,indent=2)+'\n');print('errors',len(errors),'cases',len(cases));return 1 if errors else 0
if __name__=='__main__':sys.exit(main())
