#!/usr/bin/env python3
"""Run saved fake fixture with selected Gradle-built classes; no real MOD is launched."""
import argparse,hashlib,json,os,pathlib,re,shutil,subprocess,sys,urllib.parse
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--repo',type=pathlib.Path,required=True)
parser.add_argument('--actual',type=pathlib.Path,required=True)
parser.add_argument('--output',type=pathlib.Path,required=True)
parser.add_argument('--expected-commit',required=True)
parser.add_argument('--java-home',type=pathlib.Path,required=True)
parser.add_argument('--dependencies-json',type=pathlib.Path,required=True)
args=parser.parse_args()
ROOT=args.repo.resolve();ACTUAL=args.actual.resolve();OUT=args.output.absolute();EXPECTED_COMMIT=args.expected_commit
CASES=('offense-swap','offense-same-uuid','offense-same','offense-player','offense-empty','offense-client','offense-removed','offense-level','initial-player','initial-empty','initial-client','no-target','no-gun','terrain','seed-no-target','seed-target-missing','seed-no-gun','seed-risk','energy','energy-claimed','energy-direct','defensive-proposal','defensive-claimed','collision','risk-only','wrapper-proposal','wrapper-empty','synthetic-null','getter-provider-pilot-runtime','getter-provider-pilot-error','getter-provider-level-runtime','getter-provider-level-error','getter-write-pilot-runtime','getter-write-pilot-error','getter-write-level-runtime','getter-write-level-error')
NAMES=('AirCombatManeuverManager.class','AirCombatManeuverManager$1.class','AirCombatManeuverManager$AimSolution.class','AirCombatManeuverManager$CombatContext.class','AirCombatManeuverManager$OffensiveEvaluation.class','AirCombatManeuverManager$State.class','ControlAuthorityArbiter.class','ControlAuthorityArbiter$Authority.class','ControlAuthorityArbiter$DefensiveAttempt.class','ControlAuthorityArbiter$PendingDecision.class','FighterCombatFacade.class','FighterCombatFacade$CombatEvaluation.class')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def inventory(path):return {str(p.relative_to(path)):sha(p) for p in sorted(path.rglob('*')) if p.is_file()}
def valid_origin(value, expected):
 origin=urllib.parse.urlsplit(value)
 decoded=pathlib.Path(urllib.parse.unquote(origin.path))
 return (origin.scheme=='file' and not origin.netloc and not origin.query and not origin.fragment
         and decoded.is_absolute() and decoded.resolve()==expected.resolve())
def main():
 java_env=os.environ.copy();removed_java_env={key:bool(key in java_env) for key in ('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','JDK_JAVAC_OPTIONS')};[java_env.pop(key,None) for key in removed_java_env]
 OUT.mkdir(mode=0o700);report={'removed_java_environment_variables_present':removed_java_env,'scope':'Gradle-built arbiter/offensive/facade classes in a synthetic fixture. No Minecraft runtime, world, physical motion or native setter success. Deliberate sentinels are not passes.','runs':{},'errors':[]};errors=report['errors']
 def check(c,m):
  if not c:errors.append(m)
 src=ACTUAL/'classes';stage=OUT/'classes'; build=ROOT/'ww-debug-benchmark/build/classes/java/main/com/wwdebug/autopilot';report['actual_report_sha256']=sha(ACTUAL/'report.json');actual=json.loads((ACTUAL/'report.json').read_text());report['actual_provenance']=(actual['mode']=='actual' and actual['source_copy_equal'] and not actual['patch_files'] and all(actual['source_hashes'][k]==v for k,v in actual['expected_source_hashes'].items()));check(report['actual_provenance'] and actual['inputs_unchanged'] and actual['classpath_unchanged'] and actual['stage_stable'],'saved actual source provenance')
 check(set(actual['runs'])==set(CASES)|{'compile'},'case set mismatch');check(actual['runs'].get('compile',{}).get('exit')==0,'saved compile did not pass')
 depsfile=args.dependencies_json.resolve();depvalues=json.loads(depsfile.read_text());check(isinstance(depvalues,list) and bool(depvalues) and all(isinstance(x,str) and x and pathlib.Path(x).is_absolute() and os.pathsep not in x and '\n' not in x and '\r' not in x for x in depvalues),'invalid dependency list')
 if errors:
  (OUT/'report.json').write_text(json.dumps(report,indent=2)+'\n');return 1
 deps=[pathlib.Path(x) for x in depvalues];check(len(depvalues)==len(set(depvalues)),'duplicate dependency');check(all(d.is_dir() or (d.is_file() and d.suffix.lower() in ('.jar','.zip')) for d in deps),'dependency must be an existing directory, jar or zip');java=args.java_home.resolve()/'bin/java';javac=args.java_home.resolve()/'bin/javac';check(all(p.is_file() and os.access(p,os.X_OK) for p in (java,javac)),'JDK executables missing')
 if errors:
  (OUT/'report.json').write_text(json.dumps(report,indent=2)+'\n');return 1
 dep_hashes={str(f):sha(f) for d in deps for f in (sorted(x for x in d.rglob('*') if x.is_file()) if d.is_dir() else [d])};check(dep_hashes==actual['classpath_before'],'dependency inventory differs from saved run');report['explicit_inputs']={'dependencies_json':str(depsfile),'dependencies_json_sha256':sha(depsfile),'classpath_sha256':dep_hashes,'java':str(java),'java_sha256':sha(java),'javac':str(javac),'javac_sha256':sha(javac),'argv_source':'explicit JDK, classpath and fixed local case list; saved argv is never executed'}
 git=subprocess.run(['git','rev-parse','HEAD'],cwd=ROOT,capture_output=True,text=True);report['git_head']=git.stdout.strip();report['git_exit']=git.returncode;check(git.returncode==0 and report['git_head']==EXPECTED_COMMIT,'commit mismatch')
 status=subprocess.run(['git','status','--porcelain','--untracked-files=no'],cwd=ROOT,capture_output=True,text=True);report['git_status_argv']=['git','status','--porcelain','--untracked-files=no'];report['git_status_exit']=status.returncode;report['git_status']=status.stdout;check(status.returncode==0 and not status.stdout,'tracked worktree not clean; untracked files are not inspected')
 for name in ('AirCombatManeuverManager','ControlAuthorityArbiter','FighterCombatFacade'):
  source=ROOT/'ww-debug-benchmark/src/main/java/com/wwdebug/autopilot'/(name+'.java');check(source.is_file() and sha(source)==actual['source_hashes'][name],'source differs from actual run '+name)
 for p,h in actual['compiled_classes'].items():check(pathlib.Path(p).is_file() and sha(pathlib.Path(p))==h,'source fixture class changed: '+p)
 for p,h in actual['classpath_before'].items():check(pathlib.Path(p).is_file() and sha(pathlib.Path(p))==h,'classpath changed: '+p)
 if errors:
  (OUT/'report.json').write_text(json.dumps(report,indent=2)+'\n');return 1
 shutil.copytree(src,stage)
 # The saved source fixture's fake Gun differs from the fixed production generic
 # MountedWeapon type. Compile a renamed fake only, retaining its fake behavior.
 original=ACTUAL/'stubs/com/wwdebug/benchmark/ReflectiveArmament.java';fake_dir=OUT/'fake-adjusted/com/wwdebug/benchmark';fake_dir.mkdir(parents=True);fake=fake_dir/'ReflectiveArmament.java';original_text=original.read_text();check(len(re.findall(r'\bGun\b',original_text))==3,'unexpected fake Gun source');fake.write_text(re.sub(r'\bGun\b','MountedWeapon',original_text));report['fake_adjustment']={'original':str(original),'original_sha256':sha(original),'adjusted':str(fake),'adjusted_sha256':sha(fake),'note':'type rename in artificial fake only; no real weapon is exercised'}
 empty=OUT/'empty-sourcepath';empty.mkdir();cp=os.pathsep.join(map(str,deps));argv=[str(javac),'-proc:none','--release','17','-cp',str(stage)+os.pathsep+cp,'-sourcepath',str(empty),'-d',str(stage),str(fake)];r=subprocess.run(argv,capture_output=True,timeout=30,env=java_env);(OUT/'fake-compile.stdout').write_bytes(r.stdout);(OUT/'fake-compile.stderr').write_bytes(r.stderr);report['fake_adjustment'].update({'javac_argv':argv,'exit':r.returncode,'stdout_sha256':sha(OUT/'fake-compile.stdout'),'stderr_sha256':sha(OUT/'fake-compile.stderr'),'original_sha256_after':sha(original),'adjusted_sha256_after':sha(fake)});check(r.returncode==0,'adjusted fake compile failed')
 if errors:
  (OUT/'report.json').write_text(json.dumps(report,indent=2)+'\n');return 1
 d=stage/'com/wwdebug/autopilot';fixture_before={n:sha(d/n) for n in NAMES};built_before={n:sha(build/n) for n in NAMES}
 origin_cases={'file_one_slash':('file:'+str(stage),True),'canonical_uri':(stage.as_uri(),True),
               'remote_host':('file://remote'+str(stage),False),'localhost':('file://localhost'+str(stage),False),
               'different_path':((stage.parent/'different').as_uri(),False),'relative':('file:classes',False),
               'other_scheme':('https://example.invalid'+str(stage),False),'query':(stage.as_uri()+'?x=1',False),
               'fragment':(stage.as_uri()+'#x',False),'encoded_name':(stage.parent.as_uri()+'/clas%73es',True)}
 report['origin_self_checks']={k:{'value':value,'expected':want,'actual':valid_origin(value,stage)} for k,(value,want) in origin_cases.items()}
 for name,item in report['origin_self_checks'].items():check(item['actual']==item['expected'],'origin self-check '+name)
 if errors:
  (OUT/'report.json').write_text(json.dumps(report,indent=2)+'\n');return 1
 for name in NAMES:shutil.copyfile(build/name,d/name)
 staged={n:sha(d/n) for n in NAMES};report['fixture_original_sha256']=fixture_before;report['built_before_sha256']=built_before;report['staged_before_sha256']=staged
 check(staged==built_before,'staged built class hash mismatch')
 def filt(t):return '\n'.join(x for x in t.splitlines() if 'WARN Advanced terminal features are not available in this environment' not in x)
 for name in CASES:
  entry=actual['runs'][name]
  argv=[str(java),'-Xmx128m','-Xverify:all','-Xlog:class+load=info:file='+str(OUT/(name+'.classes.log')),'-cp',str(stage)+os.pathsep+cp,'com.wwdebug.autopilot.Probe',name]
  stage_before=inventory(stage);r=subprocess.run(argv,cwd=OUT,capture_output=True,text=True,timeout=30,env=java_env);stage_after=inventory(stage);sout=OUT/(name+'.stdout');serr=OUT/(name+'.stderr');sout.write_text(r.stdout);serr.write_text(r.stderr);classlog=OUT/(name+'.classes.log');check(stage_before==stage_after,name+' staged inventory changed');check(classlog.is_file(),name+' missing class log')
  ref=ACTUAL/(name+'.stdout');equal=filt(r.stdout)==filt(ref.read_text());check(r.returncode==entry['exit'],name+' exit differs');check(equal,name+' stdout differs')
  report['runs'][name]={'argv':argv,'exit':r.returncode,'expected_exit':entry['exit'],'stdout_sha256':sha(sout),'stderr_sha256':sha(serr),'source_stdout_sha256':sha(ref),'stdout_equal_excluding_terminal_warning':equal,'stage_before':stage_before,'stage_after':stage_after,'class_log_sha256_immediate':sha(classlog) if classlog.is_file() else None}
 check(len(report['runs'])==36,'case count')
 loaded={};
 for name in report['runs']:
  p=OUT/(name+'.classes.log');check(p.is_file() and sha(p)==report['runs'][name]['class_log_sha256_immediate'],name+' class log changed');lines=p.read_text().splitlines()
  for n in NAMES:
   cls='com.wwdebug.autopilot.'+n[:-6]; found=[line for line in lines if ('] '+cls+' source:') in line]
   if found:
    loaded.setdefault(n,0);loaded[n]+=1
    for line in found:
     valid=valid_origin(line.split(' source: ',1)[1],stage)
     check(valid,name+' unexpected class origin '+n)
 report['loaded_counts']=loaded;report['target_class_union']=list(NAMES);report['target_classes_not_observed_loaded']=sorted(set(NAMES)-set(loaded));report['dynamic_lambda_scope']='Runtime generated lambda classes are not treated as physical target files or included in fixed-origin assertions.'
 check(all(n in loaded for n in ('ControlAuthorityArbiter.class','AirCombatManeuverManager.class','FighterCombatFacade.class')),'target classes not loaded')
 report['built_after_sha256']={n:sha(build/n) for n in NAMES};report['staged_after_sha256']={n:sha(d/n) for n in NAMES};check(report['built_after_sha256']==built_before,'build classes changed');check(report['staged_after_sha256']==staged,'staged classes changed')
 dep_after={str(f):sha(f) for d in deps for f in (sorted(x for x in d.rglob('*') if x.is_file()) if d.is_dir() else [d])};report['explicit_inputs']['classpath_after_sha256']=dep_after;check(dep_after==dep_hashes,'dependency inventory changed after');check(sha(java)==report['explicit_inputs']['java_sha256'] and sha(javac)==report['explicit_inputs']['javac_sha256'],'JDK executable changed')
 script=pathlib.Path(__file__).resolve();report['script_sha256']=sha(script);(OUT/'report.json').write_text(json.dumps(report,indent=2)+'\n');print('cases',len(report['runs']),'errors',len(errors));return 1 if errors else 0
if __name__=='__main__':sys.exit(main())
