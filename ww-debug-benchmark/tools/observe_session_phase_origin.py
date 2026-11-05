#!/usr/bin/env python3
"""Observe dispatch and transition phases in private copies of #214 session.

The instrumented copy is test-only: the trace may perturb execution, uses fake
world and logger, and is not an input authority or a runtime/Mixin observation.
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

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent/'src/main/java/com/wwdebug/autopilot'
NAMES=['ControlAuthorityArbiter','FormationFlightManager','AirspaceSafetyProbe','MobPilotGate',
       'ControlOutcome','ControlProposal','FlightControlOutput','FlightPhase','AutopilotSession',
       'FlightProfile','AutonomousFlightManager']
CASES=['unchanged','heading','turntimeout','missiontimeout','prestall','postterrain',
       'eventexception','frameexception']

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def once(value, old, new):
    if value.count(old)!=1:raise ValueError('anchor mismatch: '+old[:100])
    return value.replace(old,new,1)

TRACE='''package com.wwdebug.autopilot;
public class PhaseTrace {
 static FlightPhase entry,dispatch,afterPlan,exit; static FlightControlOutput planOutput,output;
 static boolean terminal,emergency;
 static void entry(FlightPhase p){entry=p;}
 static void terminal(FlightPhase p,FlightControlOutput o){terminal=true;exit=p;output=o;}
 static void dispatch(FlightPhase p){dispatch=p;}
 static void plan(FlightPhase p,FlightControlOutput o){afterPlan=p;planOutput=o;}
 static void emergency(){emergency=true;}
 static void finish(FlightPhase p,FlightControlOutput o){exit=p;output=o;}
}'''

PROBE=r'''package com.wwdebug.autopilot;
import java.util.*; import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.entity.Entity; import net.minecraft.world.phys.Vec3;
import net.minecraft.resources.ResourceLocation;
public class Probe {
 public static FlightProfile profile=new FlightProfile(new ResourceLocation("fixture","a6m"),"fighter","turn_fighter",
  10.273020653865627,32.723952272022544,31.99485535959444,34.644173364843915,null,null,43.63193636269672);
 static void set(AutopilotSession s,String field,Object value)throws Exception {
  var f=AutopilotSession.class.getDeclaredField(field);f.setAccessible(true);f.set(s,value);
 }
 static String fmt(FlightControlOutput o){return o==null?"null":String.format(java.util.Locale.ROOT,
  "%s|%s|%.8f|%.8f|%.8f|%.8f|%.8f|%.8f|%s|%s",o.reason(),o.safetyOverride(),o.x(),o.y(),o.z(),
  o.engineTarget(),o.targetAltitude(),o.targetSpeedBps(),o.stallRisk(),o.terrainRisk());}
 public static void main(String[] args)throws Exception{
  String c=args[0]; boolean traced=Boolean.parseBoolean(args[1]);
  Entity e=new Entity(new UUID(0,2),new ServerLevel());e.vel=new Vec3(0,0,(c.equals("prestall")?5.0:20.0)/20.0);
  e.pos=new Vec3(0,100,0);e.agl=c.equals("postterrain")?23.0:100.0;e.look=new Vec3(0,0,1);e.yaw=0;e.pitch=0;
  AutopilotSession session=new AutopilotSession(e,profile);
  set(session,"phase",FlightPhase.TURN_RIGHT); set(session,"phaseTicks",c.equals("turntimeout")?440:100);
  set(session,"missionTicks",c.equals("missiontimeout")?16000:1000);
  set(session,"phaseTargetYaw",c.equals("heading")||c.equals("eventexception")?5f:44f);
  if(c.equals("eventexception"))AutopilotLogManager.failEvent=true;
  if(c.equals("frameexception"))AutopilotLogManager.failFrame=true;
  FlightControlOutput result=null; Throwable thrown=null;
  try{result=session.tick(null,e);}catch(Throwable ex){thrown=ex;}
  System.out.println("CASE "+c);
  System.out.println("STATE phase="+session.phase()+" phaseTicks="+session.phaseTicks()+" missionTicks="+session.missionTicks()+" transition="+session.transitionReason());
  System.out.println("OUTPUT "+fmt(result));System.out.println("LAST "+fmt(session.lastOutput()));
  System.out.println("EVENTS "+AutopilotLogManager.events);System.out.println("FRAMES "+AutopilotLogManager.frames);
  System.out.println("THROWN "+(thrown==null?"none":thrown.getClass().getName()+":"+thrown.getMessage()+":same="+(thrown==AutopilotLogManager.FAILURE)));
  if(traced){
   System.out.println("TRACE entry="+PhaseTrace.entry+" dispatch="+PhaseTrace.dispatch+" afterPlan="+PhaseTrace.afterPlan+
      " terminal="+PhaseTrace.terminal+" emergency="+PhaseTrace.emergency+" exit="+PhaseTrace.exit+
      " planned="+fmt(PhaseTrace.planOutput)+" returned="+fmt(PhaseTrace.output));
  }
  if(c.endsWith("exception")){if(thrown!=AutopilotLogManager.FAILURE)throw new AssertionError("wrong sentinel");return;}
  if(thrown!=null)throw new AssertionError("unexpected exception",thrown);
  if(traced){
   if(PhaseTrace.entry!=FlightPhase.TURN_RIGHT||PhaseTrace.output!=result||PhaseTrace.exit!=session.phase())throw new AssertionError("trace not reached");
   if(c.equals("missiontimeout")){if(!PhaseTrace.terminal||PhaseTrace.dispatch!=null||PhaseTrace.afterPlan!=null||session.phase()!=FlightPhase.ABORTED)throw new AssertionError("terminal path");}
   else if(c.equals("prestall")){if(PhaseTrace.dispatch!=FlightPhase.STALL_RECOVERY||session.phase()!=FlightPhase.STALL_RECOVERY||PhaseTrace.terminal||PhaseTrace.emergency)throw new AssertionError("preplan stall");}
   else if(c.equals("postterrain")){if(PhaseTrace.dispatch!=FlightPhase.TURN_RIGHT||PhaseTrace.afterPlan!=FlightPhase.TURN_RIGHT||!PhaseTrace.emergency||!result.safetyOverride().equals("terrain_recovery")||PhaseTrace.planOutput==result)throw new AssertionError("postplan override");}
   else if(c.equals("heading")){if(PhaseTrace.dispatch!=FlightPhase.TURN_RIGHT||PhaseTrace.afterPlan!=FlightPhase.STALL_SETUP||!result.safetyOverride().equals("turn_speed_recovery"))throw new AssertionError("heading transition");}
   else if(c.equals("turntimeout")){if(PhaseTrace.dispatch!=FlightPhase.TURN_RIGHT||PhaseTrace.afterPlan!=FlightPhase.ABORTED||!result.safetyOverride().equals("turn_speed_recovery"))throw new AssertionError("turn timeout");}
   else if(PhaseTrace.dispatch!=FlightPhase.TURN_RIGHT||PhaseTrace.afterPlan!=FlightPhase.TURN_RIGHT||PhaseTrace.emergency||PhaseTrace.terminal)throw new AssertionError("no transition");
  }
 }
}'''

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--java-home',type=Path,required=True)
    p.add_argument('--dependencies-json',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();out=args.output.absolute();out.mkdir(mode=0o700)
    fixture_path=HERE/'test_formation_recorded_turn_observation.py'
    spec=importlib.util.spec_from_file_location('prior_fixture',fixture_path)
    fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)
    stubs=dict(fixture.STUBS)
    stubs['com/wwdebug/benchmark/WWDebugBenchmarkMod.java']='''package com.wwdebug.benchmark;
public class WWDebugBenchmarkMod { public static final org.slf4j.Logger LOGGER=org.slf4j.LoggerFactory.getLogger("fixture"); }'''
    logger=stubs['com/wwdebug/autopilot/AutopilotLogManager.java']
    logger=once(logger,'public static List<String> frames=',
                'public static boolean failEvent,failFrame; public static final RuntimeException FAILURE=new IllegalStateException("fixture-sentinel"); public static List<String> frames=')
    logger=once(logger,'p){events.add(t+":"+r);}',
                'p){if(failEvent)throw FAILURE;events.add(t+":"+r);}')
    logger=once(logger,'s,Entity e,JsonObject f){frames.add(f.toString());}',
                's,Entity e,JsonObject f){if(failFrame)throw FAILURE;frames.add(f.toString());}')
    stubs['com/wwdebug/autopilot/AutopilotLogManager.java']=logger
    stubs['com/wwdebug/autopilot/Probe.java']=PROBE
    stubs['com/wwdebug/autopilot/PhaseTrace.java']=TRACE
    originals={n:(ROOT/(n+'.java')).read_bytes() for n in NAMES}
    session=originals['AutopilotSession'].decode('utf-8')
    session=once(session,'        FlightSnapshot snapshot = FlightSnapshot.capture(aircraft);\n        missionTicks++;',
                 '        PhaseTrace.entry(phase);\n        FlightSnapshot snapshot = FlightSnapshot.capture(aircraft);\n        missionTicks++;')
    session=once(session,'            lastOutput = terminal;\n            return terminal;',
                 '            lastOutput = terminal;\n            PhaseTrace.terminal(phase, terminal);\n            return terminal;')
    session=once(session,'        FlightControlOutput output = plan(server, aircraft, snapshot);',
                 '        PhaseTrace.dispatch(phase);\n        FlightControlOutput output = plan(server, aircraft, snapshot);\n        PhaseTrace.plan(phase, output);')
    session=once(session,'            output = control(aircraft, snapshot, output.desiredDirection(),',
                 '            PhaseTrace.emergency();\n            output = control(aircraft, snapshot, output.desiredDirection(),')
    session=once(session,'        lastOutput = output;\n        return output;',
                 '        lastOutput = output;\n        PhaseTrace.finish(phase, output);\n        return output;')
    deps=[Path(x) for x in json.loads(args.dependencies_json.read_text()) if not Path(x).is_dir()]
    if not deps or any(not x.is_absolute() or not x.exists() for x in deps):raise ValueError('invalid dependency archives')
    java,javac=args.java_home/'bin/java',args.java_home/'bin/javac';cp=os.pathsep.join(map(str,deps))
    inputs={str(ROOT/(n+'.java')):hashlib.sha256(originals[n]).hexdigest() for n in NAMES}
    report={'base':'dca16d1486076e17fe70e19a9fba4a8832bf62d8','source_inputs':inputs,
            'runner_sha256':sha(Path(__file__)),'fixture_sha256':sha(fixture_path),
            'jdk_java_sha256':sha(java),'jdk_javac_sha256':sha(javac),
            'dependencies':{str(x):sha(x) for x in deps},'runs':{},
            'scope':'Private test-only source-copy trace; fake logger/snapshot/world, not a control decision or Mixin/runtime proof.'}
    shutil.copyfile(__file__,out/'runner-snapshot.py');shutil.copyfile(fixture_path,out/'fixture-snapshot.py')
    for mode in ('baseline','traced'):
        folder=out/mode;src=folder/'src';classes=folder/'classes';src.mkdir(parents=True);classes.mkdir();paths=[]
        for name,data in originals.items():
            dest=src/'prod'/(name+'.java');dest.parent.mkdir(parents=True,exist_ok=True)
            dest.write_bytes(session.encode('utf-8') if mode=='traced' and name=='AutopilotSession' else data);paths.append(dest)
        for name,data in stubs.items():
            dest=src/'fixture'/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(data,encoding='utf-8');paths.append(dest)
        def run(label,argv):
            result=subprocess.run(argv,cwd=folder,capture_output=True,text=True,timeout=30)
            (folder/(label+'.stdout')).write_text(result.stdout,encoding='utf-8')
            (folder/(label+'.stderr')).write_text(result.stderr,encoding='utf-8')
            report['runs'][mode+'/'+label]={'argv':argv,'exit':result.returncode}
            print(mode,label,result.returncode,flush=True);return result.returncode
        rc=run('compile',[str(javac),'-encoding','UTF-8','-proc:none','--release','17','-cp',cp,
                          '-sourcepath',str(folder/'empty'),'-d',str(classes),*map(str,paths)])
        if rc:continue
        for case in CASES:
            run(case,[str(java),'-Xmx128m','-Xverify:all','-Xlog:class+load=info:file='+str(folder/(case+'.classes.log')),
                      '-cp',str(classes)+os.pathsep+cp,'com.wwdebug.autopilot.Probe',case,str(mode=='traced').lower()])
    report['source_unchanged']=all(sha(ROOT/(n+'.java'))==inputs[str(ROOT/(n+'.java'))] for n in NAMES)
    report['runner_unchanged']=sha(Path(__file__))==report['runner_sha256']
    report['fixture_unchanged']=sha(fixture_path)==report['fixture_sha256']
    report['dependencies_unchanged']=all(sha(Path(k))==v for k,v in report['dependencies'].items())
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    return 0 if len(report['runs'])==2*(1+len(CASES)) and all(v['exit']==0 for v in report['runs'].values()) and all(report[x] for x in ('source_unchanged','runner_unchanged','fixture_unchanged','dependencies_unchanged')) else 1

if __name__=='__main__':sys.exit(main())
