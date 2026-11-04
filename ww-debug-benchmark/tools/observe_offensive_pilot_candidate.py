#!/usr/bin/env python3
"""Test-only copied-source offensive pilot candidate; no MOD runtime."""
import argparse,difflib,hashlib,json,os,pathlib,shutil,subprocess,sys
ROOT=pathlib.Path(__file__).resolve().parents[1]/'src/main/java'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def once(s,a,b):
 if s.count(a)!=1:raise ValueError('expected one source anchor: '+a[:100])
 return s.replace(a,b,1)
def offensive(s):
 s=once(s,'import net.minecraft.world.entity.LivingEntity;\n','import net.minecraft.world.entity.LivingEntity;\nimport net.minecraft.world.entity.Mob;\n')
 s=once(s,'    public static Optional<ControlProposal> applyControl(Entity aircraft) {\n','''    public static Optional<ControlProposal> applyControl(Entity aircraft) {
        return evaluateWithPilot(aircraft).proposal();
    }

    record OffensiveEvaluation(Optional<ControlProposal> proposal, Mob pilot, ServerLevel level) {
    }

    static OffensiveEvaluation evaluateWithPilot(Entity aircraft) {
''')
 start=s.index('    static OffensiveEvaluation evaluateWithPilot(');end=s.index('    public static boolean active(',start);head,body,tail=s[:start],s[start:end],s[end:]
 body=once(body,'        if (!MobPilotGate.isMobPiloted(aircraft) || status.isEmpty()','        Mob pilot = MobPilotGate.pilotOf(aircraft).orElse(null);\n        if (pilot == null || status.isEmpty()')
 if body.count('return Optional.empty();')!=8:raise ValueError('unexpected empty return count')
 body=body.replace('return Optional.empty();','return new OffensiveEvaluation(Optional.empty(), null, null);')
 body=once(body,'''        return Optional.of(ControlProposal.fromGuidance(
                ControlAuthorityArbiter.Authority.OFFENSIVE_COMBAT, output));''','''        return new OffensiveEvaluation(Optional.of(ControlProposal.fromGuidance(
                ControlAuthorityArbiter.Authority.OFFENSIVE_COMBAT, output)), pilot, level);''')
 return head+body+tail

def facade(s):
 s=once(s,'''    record CombatEvaluation(ControlOutcome outcome, Mob defensivePilot, ServerLevel defensiveLevel,
                            boolean defensiveProposal) {
    }''','''    record CombatEvaluation(ControlOutcome outcome, Mob defensivePilot, ServerLevel defensiveLevel,
                            boolean defensiveProposal, AirCombatManeuverManager.OffensiveEvaluation offensive) {
        CombatEvaluation(ControlOutcome outcome, Mob defensivePilot, ServerLevel defensiveLevel,
                         boolean defensiveProposal) {
            this(outcome, defensivePilot, defensiveLevel, defensiveProposal, null);
        }
    }''')
 return once(s,'''        Optional<ControlProposal> offensive = AirCombatManeuverManager.applyControl(aircraft);
        return new CombatEvaluation(offensive.map(ControlOutcome::proposed).orElseGet(ControlOutcome::none),
                null, null, false);''','''        AirCombatManeuverManager.OffensiveEvaluation offensive = AirCombatManeuverManager.evaluateWithPilot(aircraft);
        return new CombatEvaluation(offensive.proposal().map(ControlOutcome::proposed).orElseGet(ControlOutcome::none),
                null, null, false, offensive);
''')

def arbiter(s):
 s=once(s,'''                } else if (!attemptPendingWrite(aircraft, combat.pendingWrite().get())) {
                    return rejected(aircraft);
                }''','''                } else if (combatEvaluation.offensive() != null
                        && combatEvaluation.offensive().proposal().isPresent()) {
                    DefensiveAttempt attempt = attemptOffensivePendingWrite(
                            aircraft, combat.pendingWrite().get(), combatEvaluation.offensive());
                    if (attempt == DefensiveAttempt.IDENTITY_MISMATCH) {
                        return new PendingDecision(Authority.NONE, false);
                    }
                    if (attempt == DefensiveAttempt.REJECTED) {
                        return rejected(aircraft);
                    }
                } else if (!attemptPendingWrite(aircraft, combat.pendingWrite().get())) {
                    return rejected(aircraft);
                }''')
 marker='    // True means the adapter was called, not that the native setters succeeded.\n'
 return once(s,marker,'''    // ATTEMPTED means the adapter was called; native setter success is not established.
    private static DefensiveAttempt attemptOffensivePendingWrite(Entity aircraft, ControlProposal proposal,
            AirCombatManeuverManager.OffensiveEvaluation evaluation) {
        if (aircraft.isRemoved()) {
            return DefensiveAttempt.REJECTED;
        }
        var level = aircraft.level();
        if (level.isClientSide) {
            return DefensiveAttempt.REJECTED;
        }
        var pilot = MobPilotGate.pilotOf(aircraft);
        if (pilot.isEmpty() || evaluation.pilot() == null || evaluation.level() == null) {
            return DefensiveAttempt.REJECTED;
        }
        if (pilot.get() != evaluation.pilot() || level != evaluation.level()) {
            return DefensiveAttempt.IDENTITY_MISMATCH;
        }
        ReflectiveAircraft.applyControl(aircraft, proposal.x(), proposal.y(), proposal.z(),
                proposal.engineTarget());
        return DefensiveAttempt.ATTEMPTED;
    }

'''+marker)

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--mode',choices=('baseline','candidate','actual'),required=True);p.add_argument('--expected-offensive-sha256');p.add_argument('--expected-facade-sha256');p.add_argument('--expected-arbiter-sha256');p.add_argument('--fixture',type=pathlib.Path,required=True);p.add_argument('--java-home',type=pathlib.Path,required=True);p.add_argument('--dependencies-json',type=pathlib.Path,required=True);p.add_argument('--output',type=pathlib.Path,required=True);a=p.parse_args()
 if a.mode=='actual' and not all((a.expected_offensive_sha256,a.expected_facade_sha256,a.expected_arbiter_sha256)):p.error('actual mode requires all three expected source hashes')
 fixture=a.fixture.resolve();expected_fixture='c4f6fe9de97b5491f02784ddb0ae201548833a729bbf45915b02960558631b0e'
 if sha(fixture)!=expected_fixture:raise ValueError('unexpected fixture hash')
 env={'__name__':'offensive_red_fixture','__file__':str(fixture)};exec(compile(fixture.read_bytes(),str(fixture),'exec'),env);stubs=dict(env['STUBS']);cases=env['CASES']
 # Both modes use identical fake hooks. The candidate calls evaluateWithPilot directly.
 probe=stubs['com/wwdebug/autopilot/Probe.java'];probe=once(probe,'f.getMethodName().equals("applyControl")','Set.of("applyControl","evaluateWithPilot").contains(f.getMethodName())');probe=once(probe,'f.getMethodName().equals("attemptPendingWrite")','Set.of("attemptPendingWrite","attemptOffensivePendingWrite").contains(f.getMethodName())')
 # Both modes use identical artificial sentinels and call-site hooks; they do not model runtime MOD behavior.
 probe=once(probe,' public static List<String> events=new ArrayList<>();', ''' public static final RuntimeException RUNTIME_SENTINEL=new RuntimeException("synthetic-offensive-runtime");public static final AssertionError ERROR_SENTINEL=new AssertionError("synthetic-offensive-error");public static int pilotReads,levelReads;
 public static List<String> events=new ArrayList<>();''')
 old=' public static void onPilot(Entity e){if(e==target&&inOffensive())events.add("offensive:pilot");}'
 new=''' static boolean inWriteGate(){for(var f:Thread.currentThread().getStackTrace())if(f.getClassName().equals("com.wwdebug.autopilot.ControlAuthorityArbiter")&&Set.of("attemptPendingWrite","attemptOffensivePendingWrite").contains(f.getMethodName()))return true;return false;}
 static void injectGetter(String kind){boolean selected=scenario.startsWith("getter-provider-")?inOffensive():scenario.startsWith("getter-write-")&&inWriteGate();if(selected&&scenario.contains("-"+kind+"-")){if(scenario.endsWith("-runtime"))throw RUNTIME_SENTINEL;if(scenario.endsWith("-error"))throw ERROR_SENTINEL;}}
 public static void onLevel(Entity e){if(e==target){levelReads++;if(inOffensive())events.add("offensive:level");injectGetter("level");}}
 public static void onPilot(Entity e){if(e==target){pilotReads++;if(inOffensive())events.add("offensive:pilot");injectGetter("pilot");}}'''
 probe=once(probe,old,new)
 probe=once(probe,' scenario=args[0];ServerLevel level=', ''' scenario=args[0];Thread.setDefaultUncaughtExceptionHandler((t,e)->{System.out.println("uncaught_runtime_identity="+(e==RUNTIME_SENTINEL)+" uncaught_error_identity="+(e==ERROR_SENTINEL)+" pilot_reads="+pilotReads+" level_reads="+levelReads+" writes="+ReflectiveAircraft.writes+" events="+events);e.printStackTrace();System.exit(42);});ServerLevel level=''')
 anchor=' if(scenario.equals("defensive-claimed")){var setup='
 extra=''' if(scenario.equals("wrapper-proposal")||scenario.equals("wrapper-empty")){AutonomousFlightManager.applyControl(a);ReflectiveAircraft.writes.clear();ReflectiveAircraft.pilots.clear();events.clear();pilotReads=0;levelReads=0;noThreat=scenario.equals("wrapper-empty");var result=AirCombatManeuverManager.applyControl(a);System.out.println("wrapper_present="+result.isPresent()+" active="+AirCombatManeuverManager.active(a)+" aim="+AirCombatManeuverManager.currentAim(a.getUUID(),attackerId).isPresent()+" pilot_reads="+pilotReads+" level_reads="+levelReads+" events="+events);check(ReflectiveAircraft.writes.isEmpty(),"wrapper direct setter");check(result.isPresent()==!noThreat,"wrapper proposal mismatch");check(events.indexOf("offensive:uuid")>=0&&events.indexOf("offensive:pilot")>events.indexOf("offensive:uuid"),"wrapper status before pilot");return;}
 if(scenario.equals("synthetic-null")){try{Class<?> type=Class.forName("com.wwdebug.autopilot.AirCombatManeuverManager$OffensiveEvaluation");var ctor=type.getDeclaredConstructors()[0];ctor.setAccessible(true);var evaluation=ctor.newInstance(Optional.of(ControlProposal.ofRawInputs(ControlAuthorityArbiter.Authority.OFFENSIVE_COMBAT,.2f,0f,.1f,.7f,"fake")),null,null);var method=ControlAuthorityArbiter.class.getDeclaredMethod("attemptOffensivePendingWrite",Entity.class,ControlProposal.class,type);method.setAccessible(true);Object result=method.invoke(null,a,ControlProposal.ofRawInputs(ControlAuthorityArbiter.Authority.OFFENSIVE_COMBAT,.2f,0f,.1f,.7f,"fake"),evaluation);System.out.println("synthetic_null_result="+result+" writes="+ReflectiveAircraft.writes+" marker="+markers.get(a.getUUID()));check(result.toString().equals("REJECTED")&&ReflectiveAircraft.writes.isEmpty()&&markers.get(a.getUUID())==ControlAuthorityArbiter.Authority.ENERGY_FIGHTER_REENGAGEMENT,"null token did not reject");}catch(ClassNotFoundException missing){System.out.println("CLASSIFICATION=BASELINE_HELPER_ABSENT");}return;}
'''
 probe=once(probe,anchor,extra+anchor)
 probe=once(probe,'System.out.println("events="+events);','System.out.println("getter_counts=pilot:"+pilotReads+",level:"+levelReads);System.out.println("events="+events);')
 probe=once(probe,'check(ReflectiveAircraft.writes.size()==1,"CONTRACT: no stale offensive pending after pilot swap");return;', 'check(ReflectiveAircraft.writes.size()==1,"CONTRACT: no stale offensive pending after pilot swap");check(authority==ControlAuthorityArbiter.Authority.NONE&&markers.get(a.getUUID())==ControlAuthorityArbiter.Authority.ENERGY_FIGHTER_REENGAGEMENT,"swap rejection authority/marker");return;')
 probe=once(probe,' if(scenario.equals("offense-level")){System.out.println("CLASSIFICATION=LEVEL_SWAP_OBSERVATION_ONLY");return;}',''' if(scenario.equals("offense-level")){check(a.world!=level,"level was not swapped");check(ReflectiveAircraft.writes.size()==1,"CONTRACT: no offensive pending after level swap");check(authority==ControlAuthorityArbiter.Authority.NONE&&markers.get(a.getUUID())==ControlAuthorityArbiter.Authority.ENERGY_FIGHTER_REENGAGEMENT,"level rejection authority/marker");return;}''')
 entity=stubs['net/minecraft/world/entity/Entity.java'];entity=once(entity,'public Level level(){return world;}','public Level level(){com.wwdebug.autopilot.Probe.onLevel(this);return world;}');stubs['net/minecraft/world/entity/Entity.java']=entity;stubs['com/wwdebug/autopilot/Probe.java']=probe
 cases=cases+('wrapper-proposal','wrapper-empty','synthetic-null')+tuple('getter-'+scope+'-'+kind+'-'+exc for scope in ('provider','write') for kind in ('pilot','level') for exc in ('runtime','error'))
 out=a.output.absolute();out.mkdir(mode=0o700);src=out/'source-copy';fake=out/'stubs';classes=out/'classes';empty=out/'empty';[x.mkdir() for x in (src,fake,classes,empty)]
 jdk=a.java_home.resolve()/'bin';depsfile=a.dependencies_json.resolve();deps=[pathlib.Path(x) for x in json.loads(depsfile.read_text())]
 if not deps or any(not d.is_absolute() or not d.exists() for d in deps):raise ValueError('absolute existing classpath required')
 names=['ControlAuthorityArbiter','FormationFlightManager','AirspaceSafetyProbe','MobPilotGate','ControlOutcome','ControlProposal','FlightControlOutput','FlightPhase','AutopilotSession','FlightProfile','AutonomousFlightManager','FighterCombatFacade','DefensiveAirCombatManager','DefensiveAirCombatAction','AirCombatManeuverManager','AirCombatAction','AirCombatDoctrineTuning','AutopilotDoctrine'];original=[ROOT/'com/wwdebug/autopilot'/(n+'.java') for n in names];copies=[]
 transforms={'AirCombatManeuverManager':offensive,'FighterCombatFacade':facade,'ControlAuthorityArbiter':arbiter}
 for source in original:
  text=source.read_text();modified=transforms[source.stem](text) if a.mode=='candidate' and source.stem in transforms else text
  target=src/source.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True)
  if a.mode=='actual':target.write_bytes(source.read_bytes())
  else:target.write_text(modified)
  copies.append(target)
  if modified!=text:(out/(source.stem+'.patch')).write_text(''.join(difflib.unified_diff(text.splitlines(True),modified.splitlines(True),fromfile='original/'+source.name,tofile='private-copy/'+source.name)))
 paths=[]
 for name,value in stubs.items():
  target=fake/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(value);paths.append(target)
 def inventory(entries):
  result={}
  for entry in entries:
   for item in sorted(f for f in entry.rglob('*') if f.is_file()) if entry.is_dir() else [entry]:result[str(item)]=sha(item)
  return result
 inputs=original+copies+paths+[fixture,jdk/'java',jdk/'javac',depsfile,pathlib.Path(__file__).resolve()];before=inventory(inputs);cpbefore=inventory(deps);shutil.copyfile(__file__,out/'runner-snapshot.py');arbiter_sha=sha(next(x for x in original if x.name=='ControlAuthorityArbiter.java'))
 source_hashes={x.stem:sha(x) for x in original};copy_equal=all(sha(x)==sha(y) for x,y in zip(original,copies));patches=sorted(p.name for p in out.glob('*.patch'))
 expected={'AirCombatManeuverManager':a.expected_offensive_sha256,'FighterCombatFacade':a.expected_facade_sha256,'ControlAuthorityArbiter':a.expected_arbiter_sha256}
 if a.mode=='actual':
  if not copy_equal or patches or any(source_hashes[k]!=v for k,v in expected.items()):raise ValueError('actual source/copy/patch provenance mismatch')
 elif arbiter_sha!='0bd7e22f7928de30e1c9621ae4cd16942c6723f395d7f7da278c998da4ca01c3':raise ValueError('unexpected #218 source')
 report={'scope':'#218 source, explicitly modified copies, or byte-identical actual worktree copies; fake world, snapshot, weapon, awareness, terrain, logging and setter; no MOD/runtime, actual shooting, ownership or physical safety. Fake hook supports old/new method names equally.','mode':a.mode,'fixture_sha256':sha(fixture),'source_hashes':source_hashes,'expected_source_hashes':expected,'source_copy_equal':copy_equal,'patch_files':patches,'inputs_before':before,'classpath_before':cpbefore,'runs':{}}
 def run(name,argv):
  cbefore=inventory([classes]);r=subprocess.run(argv,cwd=out,capture_output=True,text=True,timeout=30);stdout=out/(name+'.stdout');stderr=out/(name+'.stderr');stdout.write_text(r.stdout);stderr.write_text(r.stderr);log=out/(name+'.classes.log');report['runs'][name]={'argv':argv,'exit':r.returncode,'classes_before':cbefore,'classes_after':inventory([classes]),'outputs_immediate':inventory([stdout,stderr]+([log] if log.exists() else []))};print(name,r.returncode,flush=True)
 run('compile',[str(jdk/'javac'),'-proc:none','--release','17','-cp',os.pathsep.join(map(str,deps)),'-sourcepath',str(empty),'-d',str(classes),*map(str,copies),*map(str,paths)])
 if report['runs']['compile']['exit']==0:
  for case in cases:run(case,[str(jdk/'java'),'-Xmx128m','-Xverify:all','-Xlog:class+load=info:file='+str(out/(case+'.classes.log')),'-cp',str(classes)+os.pathsep+os.pathsep.join(map(str,deps)),'com.wwdebug.autopilot.Probe',case])
 report['inputs_after']=inventory(inputs);report['inputs_unchanged']=before==report['inputs_after'];report['classpath_after']=inventory(deps);report['classpath_unchanged']=cpbefore==report['classpath_after'];report['compiled_classes']=inventory([classes]);report['stage_stable']=all(x['classes_before']==x['classes_after']==report['compiled_classes'] for n,x in report['runs'].items() if n!='compile');report['runner_snapshot_sha256']=sha(out/'runner-snapshot.py');(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
 return 0 if report['inputs_unchanged'] and report['classpath_unchanged'] and report['stage_stable'] and len(report['runs'])==len(cases)+1 and all(x['exit']==0 for x in report['runs'].values()) else 1
if __name__=='__main__':sys.exit(main())
