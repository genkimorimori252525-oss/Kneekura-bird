#!/usr/bin/env python3
"""Verify saved fake offensive-control source-copy results; no MOD is run."""
import argparse,hashlib,json,pathlib,sys

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--baseline',type=pathlib.Path,required=True);p.add_argument('--candidate',type=pathlib.Path,required=True);p.add_argument('--descriptor',type=pathlib.Path,required=True);p.add_argument('--output',type=pathlib.Path,required=True);a=p.parse_args();out=a.output.absolute();out.mkdir(mode=0o700);dirs={'baseline':a.baseline.resolve(),'candidate':a.candidate.resolve()};reports={k:json.loads((v/'report.json').read_text()) for k,v in dirs.items()};errors=[];inputs=[];results={}
 def check(b,msg):
  if not b:errors.append(msg)
 intentional_red={'offense-swap','offense-same-uuid','offense-level'}
 for mode,root in dirs.items():
  r=reports[mode];check(r['mode']==mode,mode+' mode');check(r['inputs_unchanged'] and r['classpath_unchanged'] and r['stage_stable'],mode+' stability');check(len(r['runs'])==37,mode+' count');check(sha(root/'runner-snapshot.py')==r['runner_snapshot_sha256'],mode+' snapshot');inputs.extend((root/'runner-snapshot.py',root/'report.json'))
  for name,value in list(r['inputs_before'].items())+list(r['classpath_before'].items())+list(r['compiled_classes'].items()):
   f=pathlib.Path(name);inputs.append(f);check(f.is_file() and sha(f)==value,mode+' input '+name)
  for case,entry in r['runs'].items():
   expected=42 if case.startswith('getter-') or (mode=='baseline' and case in intentional_red) else 0
   check(entry['exit']==expected,f'{mode} {case} exit {entry["exit"]} expected {expected}')
   for name,value in entry['outputs_immediate'].items():
    f=pathlib.Path(name);inputs.append(f);check(f.is_file() and sha(f)==value,mode+' output '+name)
   if case!='compile':check(entry['classes_before']==entry['classes_after']==r['compiled_classes'],mode+' class staging changed '+case)
 def strip_warning(value):return '\n'.join(s for s in value.splitlines() if 'WARN Advanced terminal features are not available in this environment' not in s)
 cases=set(reports['baseline']['runs']);check(cases==set(reports['candidate']['runs']),'case names differ')
 comparable=sorted(n for n in cases if n not in intentional_red|{'compile','synthetic-null'} and not n.startswith('getter-'))
 for name in comparable:
  left=dirs['baseline']/(name+'.stdout');right=dirs['candidate']/(name+'.stdout');l,r=strip_warning(left.read_text()),strip_warning(right.read_text());check(l==r,name+' stdout differs');results[name]={'baseline_stdout_sha256':sha(left),'candidate_stdout_sha256':sha(right),'equal_without_terminal_warning':l==r}
 for name in sorted(n for n in cases if n.startswith('getter-')):
  left=dirs['baseline']/(name+'.stdout');right=dirs['candidate']/(name+'.stdout');l=[s for s in left.read_text().splitlines() if s.startswith('uncaught_')];r=[s for s in right.read_text().splitlines() if s.startswith('uncaught_')];identity='uncaught_runtime_identity=true uncaught_error_identity=false' if name.endswith('-runtime') else 'uncaught_runtime_identity=false uncaught_error_identity=true';check(len(l)==len(r)==1 and l==r and identity in l[0],name+' sentinel/count/event mismatch');results[name]={'sentinel_line_equal':l==r,'expected_identity':identity,'baseline_stdout_sha256':sha(left),'candidate_stdout_sha256':sha(right)}
 for name in intentional_red:
  left=dirs['baseline']/(name+'.stderr');right=dirs['candidate']/(name+'.stdout');expected='CONTRACT: no offensive pending after level swap' if name=='offense-level' else 'CONTRACT: no stale offensive pending after pilot swap';check(expected in left.read_text(),name+' baseline red reason');raw=right.read_text();check('authority=NONE' in raw and 'active=true aim=true' in raw and 'marker=ENERGY_FIGHTER_REENGAGEMENT' in raw,name+' candidate state')
 null=(dirs['candidate']/'synthetic-null.stdout').read_text();check('synthetic_null_result=REJECTED writes=[] marker=ENERGY_FIGHTER_REENGAGEMENT' in null,'null token')
 desc=json.loads((a.descriptor/'report.json').read_text());inputs.append(a.descriptor/'report.json');check(not desc['errors'],'descriptor inspector errors');check(desc['javap_before']==desc['javap_after'] and pathlib.Path(desc['javap']).is_file() and sha(pathlib.Path(desc['javap']))==desc['javap_before'],'javap hash');inputs.append(pathlib.Path(desc['javap']))
 for name,e in desc['runs'].items():
  cls=pathlib.Path(e['argv'][-1]);stdout=a.descriptor/(name+'.stdout');stderr=a.descriptor/(name+'.stderr');inputs.extend((cls,stdout,stderr));check(e['exit']==0 and e['class_before']==e['class_after'] and sha(cls)==e['class_before'] and len(e['matching_declarations'])==1,name+' descriptor');check(sha(stdout)==e['stdout_sha256'] and sha(stderr)==e['stderr_sha256'],name+' descriptor output')
 script=pathlib.Path(__file__).resolve();inputs.append(script);data={'scope':'Saved fake source-copy results only. No real MOD/runtime/native setter or firing safety claim. Existing exceptions are artificially injected; fixture counts and events are not real-world measurements. Record-component reflection and generated methods may differ.','errors':errors,'comparable_case_count':len(comparable),'results':results,'inputs_sha256':{str(f):sha(f) for f in dict.fromkeys(inputs) if f.is_file()},'verifier_sha256':sha(script)};(out/'report.json').write_text(json.dumps(data,indent=2)+'\n');print('errors',len(errors),'comparable',len(comparable));return 1 if errors else 0
if __name__=='__main__':sys.exit(main())
