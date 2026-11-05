#!/usr/bin/env python3
"""Compare an experimental formation target floor using #226's stand-ins.

This modifies a temporary source copy only. It does not run Minecraft or establish
aircraft safety. Every result requires review, including intentionally red cases.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent / 'src/main/java/com/wwdebug/autopilot'
NAMES = ['ControlAuthorityArbiter', 'FormationFlightManager', 'AirspaceSafetyProbe',
         'MobPilotGate', 'ControlOutcome', 'ControlProposal', 'FlightControlOutput',
         'FlightPhase', 'AutopilotSession', 'FlightProfile', 'AutonomousFlightManager']
CASES = ['1549-low', '1589-low', '1549-below', '1549-equal', '1549-above',
         '1549-high', '1549-ungrouped', '1549-leader', '1549-terrain',
         '1549-collision', '1549-player', '1549-playerlate', '1549-moblate',
         '1549-combat', '1549-missingprofile', '1589-timeout', '1589-riskonly', '1589-heading',
         '1549-nanspeed', '1549-infspeed', '1549-nanleader', '1549-fastleader',
         '1549-err08minus', '1549-err08equal', '1549-err08plus',
         '1549-err35minus', '1549-err35equal', '1549-err35plus',
         '1549-neg08minus', '1549-neg08equal', '1549-neg08plus',
         '1549-neg25minus', '1549-neg25equal', '1549-neg25plus']

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def replace_once(value, old, new):
    if value.count(old) != 1:
        raise ValueError('anchor not unique: ' + old[:100])
    return value.replace(old, new, 1)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--java-home', type=Path, required=True)
    p.add_argument('--dependencies-json', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--only', choices=CASES, help='Run one selected case in each mode')
    args = p.parse_args()
    out = args.output.absolute()
    out.mkdir(mode=0o700)  # Never reuse earlier evidence.
    fixture_file = HERE / 'test_formation_recorded_turn_observation.py'
    spec = importlib.util.spec_from_file_location('prior_fixture', fixture_file)
    fixture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture)
    stubs = dict(fixture.STUBS)
    stubs['com/wwdebug/benchmark/WWDebugBenchmarkMod.java'] = '''package com.wwdebug.benchmark;
public class WWDebugBenchmarkMod { public static final org.slf4j.Logger LOGGER=org.slf4j.LoggerFactory.getLogger("fixture"); }'''
    checkpoint = stubs['com/wwdebug/autopilot/AutopilotValidationCheckpoint.java']
    checkpoint = replace_once(checkpoint, 'static int ticks=439, calls;',
                              'static int ticks=439, calls; static float targetYaw=44.555055f;')
    checkpoint = replace_once(checkpoint, 'set(s,"phaseTargetYaw",44.555055f);',
                              'set(s,"phaseTargetYaw",targetYaw);')
    stubs['com/wwdebug/autopilot/AutopilotValidationCheckpoint.java'] = checkpoint
    stubs['com/wwdebug/autopilot/FighterCombatFacade.java'] = '''package com.wwdebug.autopilot;
import net.minecraft.world.entity.Entity; import net.minecraft.world.entity.Mob;
import net.minecraft.world.entity.player.Player;
public class FighterCombatFacade { public static String mode="";
 public static ControlOutcome applyControl(Entity e,boolean risk){
  if(mode.equals("playerlate")) e.pilot=new Player();
  if(mode.equals("moblate")) e.pilot=new Mob(new java.util.UUID(0,99));
  if(mode.equals("combat")) return ControlOutcome.claimedWithoutProposal(ControlAuthorityArbiter.Authority.DEFENSIVE_COMBAT);
  return ControlOutcome.none(); }}'''
    registry = stubs['com/wwdebug/autopilot/AutopilotProfileRegistry.java']
    registry = replace_once(registry, 'public static Optional<FlightProfile> ',
                            'public static int calls; public static boolean missing; public static Optional<FlightProfile> ')
    registry = replace_once(registry, 'return Optional.of(Probe.profile);',
                            'return missing && ++calls>1 ? Optional.empty():Optional.of(Probe.profile);')
    stubs['com/wwdebug/autopilot/AutopilotProfileRegistry.java'] = registry
    old_probe = stubs['com/wwdebug/autopilot/Probe.java']
    prefix = old_probe[:old_probe.index('public static void main(String[] args)')]
    stubs['com/wwdebug/autopilot/Probe.java'] = prefix + r'''
public static void main(String[] args){
 String[] bits=args[0].split("-"); int tick=Integer.parseInt(bits[0]); String kind=bits[1];
 ServerLevel l=new ServerLevel(); Entity a=new Entity(new UUID(0,2),l), leader=new Entity(new UUID(0,1),l);
 inputs(a,true,tick); inputs(leader,false,tick); a.pilot=new Mob(); leader.pilot=new Mob(new UUID(0,4));
 double floor=profile.turnSpeedFloorBps();
 if(kind.equals("below")||kind.equals("equal")||kind.equals("above")||kind.equals("high")){
  double speed=kind.equals("below")?floor-0.001:kind.equals("equal")?floor:kind.equals("above")?floor+0.001:50.0;
  a.vel=new Vec3(0,0,speed/20.0);
 }
 if(kind.startsWith("err")||kind.startsWith("neg")){
  double error=kind.startsWith("err08")?0.8:kind.startsWith("err35")?3.5:kind.startsWith("neg08")?-0.8:-2.5;
  if(kind.endsWith("minus"))error-=0.001;
  if(kind.endsWith("plus"))error+=0.001;
  a.vel=new Vec3(0,0,(floor-error)/20.0);
 }
 if(kind.equals("nanspeed")) a.vel=new Vec3(Double.NaN,0,0);
 if(kind.equals("infspeed")) a.vel=new Vec3(Double.POSITIVE_INFINITY,0,0);
 if(kind.equals("nanleader")) leader.vel=new Vec3(Double.NaN,0,0);
 if(kind.equals("fastleader")) leader.vel=new Vec3(0,0,3.0);
 if(kind.equals("collision")||kind.equals("riskonly")) leader.pos=a.pos.add(3,0,0);
 leader.tags.add("wwformation:group:g"); leader.tags.add("wwformation:leader");
 a.tags.add("wwformation:slot:2"); if(!kind.equals("ungrouped"))a.tags.add("wwformation:group:g");
 if(kind.equals("leader")){leader.tags.remove("wwformation:leader"); a.tags.add("wwformation:leader");}
 l.entities.add(a);l.entities.add(leader); TerrainAvoidancePlanner.enabled=kind.equals("terrain");
 AutopilotProfileRegistry.missing=kind.equals("missingprofile");
 FighterCombatFacade.mode=kind;
 AutopilotValidationCheckpoint.ticks=(kind.equals("timeout")||kind.equals("riskonly"))?440:(tick==1549?399:439);
 if(kind.equals("heading")) AutopilotValidationCheckpoint.targetYaw=a.yaw+5.0f;
 if(kind.equals("player")){ControlAuthorityArbiter.applyControl(a);ReflectiveAircraft.writes.clear();
  AutopilotLogManager.frames.clear();AutopilotLogManager.adapters.clear();AutopilotLogManager.outputs.clear();
  AutopilotLogManager.events.clear();a.pilot=new Player();}
 var auth=ControlAuthorityArbiter.applyControl(a);var session=AutopilotValidationCheckpoint.session;
 var mission=session.lastOutput();
 System.out.println("OBS case="+args[0]+" auth="+auth+" phase="+session.phase()+" clock="+session.phaseTicks()+" base="+(mission==null?"null":mission.safetyOverride()));
 System.out.println("WRITES "+ReflectiveAircraft.writes);
 System.out.println("ADAPTERS "+AutopilotLogManager.adapters);
 System.out.println("RISK "+AirspaceSafetyProbe.collisionRisk(a));
 if(kind.equals("player") && !ReflectiveAircraft.writes.isEmpty())throw new AssertionError("player wrote");
 if((kind.equals("playerlate")||kind.equals("moblate")) && ReflectiveAircraft.writes.size()!=1)throw new AssertionError("late-pilot gate");
 if(kind.equals("combat") && (auth!=ControlAuthorityArbiter.Authority.DEFENSIVE_COMBAT||ReflectiveAircraft.writes.size()!=1))throw new AssertionError("combat priority");
 if(kind.equals("terrain") && (auth!=ControlAuthorityArbiter.Authority.TERRAIN_AVOIDANCE||ReflectiveAircraft.writes.size()!=1))throw new AssertionError("terrain priority");
 if(kind.equals("collision") && (auth!=ControlAuthorityArbiter.Authority.COLLISION_AVOIDANCE||ReflectiveAircraft.writes.size()!=2))throw new AssertionError("collision direct");
 if((kind.equals("ungrouped")||kind.equals("leader")||kind.equals("missingprofile")) && ReflectiveAircraft.writes.size()!=1)throw new AssertionError("not a slot proposal");
 if(kind.equals("timeout")&&(session.phase()!=FlightPhase.ABORTED||ReflectiveAircraft.writes.size()!=1))throw new AssertionError("timeout transition");
 if(kind.equals("riskonly")&&(session.phase()!=FlightPhase.ABORTED||auth!=ControlAuthorityArbiter.Authority.COLLISION_AVOIDANCE||ReflectiveAircraft.writes.size()!=1||!AirspaceSafetyProbe.collisionRisk(a)))throw new AssertionError("risk-only observation");
 if(kind.equals("heading")&&session.phase()!=FlightPhase.STALL_SETUP)throw new AssertionError("heading transition");
}
}'''
    deps = [Path(x) for x in json.loads(args.dependencies_json.read_text())]
    if not deps or any(not x.is_absolute() or not x.exists() for x in deps):
        raise ValueError('classpath must contain existing absolute paths')
    # Previous fixture's project-class directory can mask missing sources: omit it.
    deps = [x for x in deps if not x.is_dir()]
    if not deps:
        raise ValueError('no archive dependencies')
    cp = os.pathsep.join(map(str, deps))
    java, javac = args.java_home / 'bin/java', args.java_home / 'bin/javac'
    original = {name: (ROOT / (name + '.java')).read_bytes() for name in NAMES}
    source_text = original['FormationFlightManager'].decode('utf-8')
    # Experiment only: use existing error-based steps, without changing axes.
    anchor = '''        float engineTarget;
        double speedError = targetSpeed - snapshot.speedBps();'''
    replacement = '''        boolean turnFloorTarget = phase == FlightPhase.TURN_RIGHT
                && Double.isFinite(snapshot.speedBps()) && Double.isFinite(targetSpeed)
                && targetSpeed < profile.turnSpeedFloorBps();
        if (turnFloorTarget) targetSpeed = profile.turnSpeedFloorBps();
        float engineTarget;
        double speedError = targetSpeed - snapshot.speedBps();'''
    candidate = replace_once(source_text, anchor, replacement).encode('utf-8')
    candidate = replace_once(candidate.decode('utf-8'),
            '                "formation_slot_tracking", "formation_tracking");',
            '                turnFloorTarget ? "formation_turn_floor_target" : "formation_slot_tracking",\n'
            '                turnFloorTarget ? "formation_turn_floor_target" : "formation_tracking");').encode('utf-8')
    inputs = {str(ROOT / (n+'.java')): hashlib.sha256(original[n]).hexdigest() for n in NAMES}
    report = {'base':'dca16d1486076e17fe70e19a9fba4a8832bf62d8', 'source_inputs':inputs,
              'runner_sha256':digest(Path(__file__)), 'fixture_sha256':digest(fixture_file),
              'jdk_java_sha256':digest(java), 'jdk_javac_sha256':digest(javac),
              'dependencies':{str(x):digest(x) for x in deps}, 'runs':{},
              'cases': [args.only] if args.only else CASES,
              'scope':'Test-only source-copy target-floor hypothesis; fake world, logger, combat, profile registry, snapshot and setter. No physics, native setter or safety proof.'}
    shutil.copyfile(__file__,out/'runner-snapshot.py')
    shutil.copyfile(fixture_file,out/'fixture-snapshot.py')
    for mode in ('baseline','candidate'):
        folder=out/mode; src=folder/'src'; classes=folder/'classes'; src.mkdir(parents=True);classes.mkdir()
        paths=[]
        for name,data in original.items():
            dest=src/'prod'/(name+'.java'); dest.parent.mkdir(parents=True,exist_ok=True)
            dest.write_bytes(candidate if mode=='candidate' and name=='FormationFlightManager' else data);paths.append(dest)
        for name,data in stubs.items():
            dest=src/'fixture'/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(data,encoding='utf-8');paths.append(dest)
        def run(label,argv):
            result=subprocess.run(argv,capture_output=True,text=True,timeout=30,cwd=folder)
            (folder/(label+'.stdout')).write_text(result.stdout,encoding='utf-8')
            (folder/(label+'.stderr')).write_text(result.stderr,encoding='utf-8')
            report['runs'][mode+'/'+label]={'argv':argv,'exit':result.returncode}
            print(mode,label,result.returncode,flush=True)
            return result.returncode
        rc=run('compile',[str(javac),'-encoding','UTF-8','-proc:none','--release','17','-cp',cp,
                           '-sourcepath',str(folder/'empty'),'-d',str(classes),*map(str,paths)])
        if rc: continue
        for case in report['cases']:
            run(case,[str(java),'-Xmx128m','-Xverify:all',
                      '-Xlog:class+load=info:file='+str(folder/(case+'.classes.log')),
                      '-cp',str(classes)+os.pathsep+cp,'com.wwdebug.autopilot.Probe',case])
    report['source_unchanged']=all(digest(ROOT/(n+'.java'))==inputs[str(ROOT/(n+'.java'))] for n in NAMES)
    report['runner_unchanged']=digest(Path(__file__))==report['runner_sha256']
    report['fixture_unchanged']=digest(fixture_file)==report['fixture_sha256']
    report['dependencies_unchanged']=all(digest(Path(k))==v for k,v in report['dependencies'].items())
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    # Cases are observations; a nonzero child makes the overall result incomplete.
    return 0 if len(report['runs'])==2*(1+len(report['cases'])) and all(v['exit']==0 for v in report['runs'].values()) and all(report[x] for x in ('source_unchanged','runner_unchanged','fixture_unchanged','dependencies_unchanged')) else 1

if __name__ == '__main__':
    sys.exit(main())
