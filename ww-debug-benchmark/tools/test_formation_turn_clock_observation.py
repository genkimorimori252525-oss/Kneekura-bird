#!/usr/bin/python3
"""Test synthetic TURN_RIGHT states using #214 AutopilotSession and existing stubs.

No Minecraft/Forge server or world is run. Output directory must be new.
"""
import argparse
import hashlib
import json
import os
import pathlib
import runpy
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
ORIGINAL = ROOT / 'tools/test_formation_turn_recovery_standalone.py'
CASES = ('pre44_at10','pre45_at10','pre439_out','pre440_out','pre440_at10')

PROBE = r'''package com.wwdebug.autopilot;
import java.util.UUID;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.phys.Vec3;
public class Probe {
  private static void set(AutopilotSession s,String field,Object value) throws Exception {
    var f=AutopilotSession.class.getDeclaredField(field); f.setAccessible(true); f.set(s,value);
  }
  public static void main(String[] args) throws Exception {
    String c=args[0]; int before=switch(c) {
      case "pre44_at10" -> 44; case "pre45_at10" -> 45;
      case "pre439_out" -> 439; case "pre440_out", "pre440_at10" -> 440;
      default -> throw new IllegalArgumentException(c);
    };
    float target=c.endsWith("at10")?10f:11f;
    Entity e=new Entity(new UUID(0,2),new ServerLevel());
    e.vel=new Vec3(0,0,30.779231357359148/20.0);
    var session=new AutopilotSession(e,AutonomousFlightManager.profile);
    set(session,"phase",FlightPhase.TURN_RIGHT); set(session,"phaseTicks",before);
    set(session,"missionTicks",1000); set(session,"phaseTargetYaw",target);
    var result=session.tick(null,e);
    System.out.println("case="+c+" before="+before+" target_heading="+target+
      " yaw=0.0 speed_bps=30.779231357359148 agl_stub=100.0 after_phase="+session.phase()+
      " after_phase_ticks="+session.phaseTicks()+" after_mission_ticks="+session.missionTicks()+
      " transition_reason="+session.transitionReason()+" output_reason="+result.reason()+
      " output_safety="+result.safetyOverride()+" output_engine="+result.engineTarget());
    FlightPhase expected=(c.equals("pre45_at10")||c.equals("pre440_at10"))?FlightPhase.STALL_SETUP:
      (c.equals("pre440_out")?FlightPhase.ABORTED:FlightPhase.TURN_RIGHT);
    int expectedTicks=(expected==FlightPhase.TURN_RIGHT)?before+1:0;
    String reason=(expected==FlightPhase.STALL_SETUP)?"right_turn_heading_reached":
      (expected==FlightPhase.ABORTED?"right_turn_timeout":"mob_pilot_session_started");
    if(session.phase()!=expected || session.phaseTicks()!=expectedTicks || session.missionTicks()!=1001
       || !session.transitionReason().equals(reason) || !result.safetyOverride().equals("turn_speed_recovery"))
      throw new AssertionError("phase/clock/reason/output mismatch");
  }
}'''

def digest(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()

def inventory(paths):
    out={}
    for p in paths:
        for f in (sorted(x for x in p.rglob('*') if x.is_file()) if p.is_dir() else [p]):
            out[str(f)]=digest(f)
    return out

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--java-home',type=pathlib.Path,required=True)
    parser.add_argument('--dependencies-json',type=pathlib.Path,required=True)
    parser.add_argument('--output',type=pathlib.Path,required=True)
    args=parser.parse_args()
    global DEPENDENCIES,JDK,OUT
    DEPENDENCIES=args.dependencies_json.resolve()
    JDK=args.java_home.resolve()/'bin'
    OUT=args.output.absolute()
    OUT.mkdir(mode=0o700)
    prod=OUT/'production';fake=OUT/'fixture';src=OUT/'stubs';empty=OUT/'empty'
    for p in (prod,fake,src,empty):p.mkdir()
    definitions=runpy.run_path(str(ORIGINAL));stubs=dict(definitions['STUBS'])
    stubs['com/wwdebug/autopilot/Probe.java']=PROBE
    paths=[]
    for name,contents in stubs.items():
        path=src/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(contents);paths.append(path)
    deps=[pathlib.Path(x) for x in json.loads(DEPENDENCIES.read_text())]
    if not deps or any(not p.is_absolute() or not p.exists() for p in deps):raise ValueError('invalid classpath')
    cp=os.pathsep.join(map(str,deps))
    names=['ControlAuthorityArbiter','FormationFlightManager','AirspaceSafetyProbe','MobPilotGate',
           'ControlOutcome','ControlProposal','FlightControlOutput','FlightPhase','AutopilotSession','FlightProfile']
    actual=[ROOT/'src/main/java/com/wwdebug/autopilot'/(n+'.java') for n in names]
    inputs=actual+paths+[JDK/'java',JDK/'javac',DEPENDENCIES,ORIGINAL,pathlib.Path(__file__)]
    before=inventory(inputs);deps_before=inventory(deps)
    shutil.copyfile(ORIGINAL,OUT/'original-runner-snapshot.py')
    shutil.copyfile(pathlib.Path(__file__),OUT/'runner-snapshot.py')
    report={'expected_base':'80eab064420c217df66c2d42c3f8772ff4216add (verify inputs_before hashes)',
       'scope':'Actual session/profile and other named source with fixture manager/snapshot/aircraft/log. State is injected, no Minecraft physics, server or world.',
       'inputs_before':before,'classpath_before':deps_before,'runs':{}}
    env={'PATH':'/usr/bin','HOME':'/nonexistent'}
    def run(name,argv):
        try:
            r=subprocess.run(argv,cwd=OUT,env=env,capture_output=True,text=True,timeout=30)
            (OUT/(name+'.stdout')).write_text(r.stdout);(OUT/(name+'.stderr')).write_text(r.stderr)
            report['runs'][name]={'argv':argv,'exit':r.returncode};print(name,r.returncode,flush=True);return r.returncode
        except subprocess.TimeoutExpired as error:
            report['runs'][name]={'argv':argv,'timeout':True};print(name,'timeout',flush=True);return 124
    rc=run('compile-production',[str(JDK/'javac'),'-encoding','UTF-8','-proc:none','--release','17','-cp',cp,'-sourcepath',str(empty),'-d',str(prod),*map(str,actual)])
    if rc==0:rc=run('compile-fixture',[str(JDK/'javac'),'-encoding','UTF-8','-proc:none','--release','17','-cp',str(prod)+os.pathsep+cp,'-sourcepath',str(empty),'-d',str(fake),*map(str,paths)])
    if rc==0:
        for case in CASES:
            rc=run(case,[str(JDK/'java'),'-Xmx128m','-Xverify:all','-Xlog:class+load=info:file='+str(OUT/(case+'.classes.log')),
                    '-cp',str(fake)+os.pathsep+str(prod)+os.pathsep+cp,'com.wwdebug.autopilot.Probe',case])
            if rc:break
    report['inputs_after']=inventory(inputs);report['inputs_unchanged']=report['inputs_after']==before
    report['classpath_after']=inventory(deps);report['classpath_unchanged']=report['classpath_after']==deps_before
    report['compiled_production']=inventory([prod]);report['compiled_fixture']=inventory([fake])
    (OUT/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    ok=(len(report['runs'])==7 and all(x.get('exit')==0 for x in report['runs'].values())
        and report['inputs_unchanged'] and report['classpath_unchanged'])
    return 0 if ok else 1

if __name__=='__main__':sys.exit(main())
