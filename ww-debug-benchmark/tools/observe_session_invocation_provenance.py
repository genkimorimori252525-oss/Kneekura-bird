#!/usr/bin/env python3
"""Test-only same-call origin scope over private #235 session source copies.

Not connected to an arbiter or Mixin. Fake world/logger/snapshot; not a runtime
freshness proof or a flight safety verdict. Baseline intentionally lacks scope.
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
CASES=['normal','heading','prestall','emergency','terminal','different','routecopy',
       'previous','exception','nested','nesteddirect','nestedforeign','foreigncall','closed','crossthread']
REDS={'normal','heading','prestall','emergency','terminal','different','routecopy','previous','closed'}

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def once(value,old,new):
    if value.count(old)!=1:raise ValueError('anchor mismatch: '+old[:100])
    return value.replace(old,new,1)

TRACE='''package com.wwdebug.autopilot;
public final class PhaseTrace {
 static final boolean SUPPORTED=__SUPPORTED__;
 private static final ThreadLocal<Frame> CURRENT=new ThreadLocal<>();
 static Frame begin(AutopilotSession owner){
  Frame parent=CURRENT.get(); for(Frame p=parent;p!=null;p=p.parent)p.invalid=true;
  Frame f=new Frame(owner,parent); if(parent!=null)f.invalid=true; CURRENT.set(f);return f;
 }
 static final class Frame implements AutoCloseable {
  final AutopilotSession owner; final Frame parent; final Thread thread=Thread.currentThread();
  boolean invalid,entered,normal,terminal,emergency,closed;
  FlightPhase entry,dispatch,afterPlan,exit; FlightControlOutput observed,returned;
  Frame(AutopilotSession s,Frame p){owner=s;parent=p;}
  void complete(FlightControlOutput o){normal=true;returned=o;if(observed!=o)invalid=true;}
  boolean known(AutopilotSession query,FlightControlOutput o){
   return SUPPORTED&&!invalid&&!closed&&thread==Thread.currentThread()&&CURRENT.get()==this
    &&owner==query&&entered&&normal&&returned!=null&&returned==observed&&returned==o
    &&exit!=null&&(terminal?dispatch==null:dispatch!=null&&afterPlan!=null);
  }
  public void close(){closed=true;if(CURRENT.get()==this)CURRENT.set(parent);else invalid=true;}
 }
 private static Frame frame(AutopilotSession s){
  Frame f=CURRENT.get();if(f==null)return null;
  if(f.owner!=s){f.invalid=true;return null;}return f;
 }
 static void entry(AutopilotSession s,FlightPhase p){Frame f=frame(s);if(f!=null){if(f.entered)f.invalid=true;f.entered=true;f.entry=p;}}
 static void terminal(AutopilotSession s,FlightPhase p,FlightControlOutput o){Frame f=frame(s);if(f!=null){f.terminal=true;f.exit=p;f.observed=o;}}
 static void dispatch(AutopilotSession s,FlightPhase p){Frame f=frame(s);if(f!=null)f.dispatch=p;}
 static void plan(AutopilotSession s,FlightPhase p,FlightControlOutput o){Frame f=frame(s);if(f!=null)f.afterPlan=p;}
 static void emergency(AutopilotSession s){Frame f=frame(s);if(f!=null)f.emergency=true;}
 static void finish(AutopilotSession s,FlightPhase p,FlightControlOutput o){Frame f=frame(s);if(f!=null){f.exit=p;f.observed=o;}}
}'''

PROBE=r'''package com.wwdebug.autopilot;
import java.util.*; import net.minecraft.server.level.ServerLevel; import net.minecraft.world.entity.Entity;
import net.minecraft.world.phys.Vec3;import net.minecraft.resources.ResourceLocation;
public class Probe {
 public static FlightProfile profile=new FlightProfile(new ResourceLocation("fixture","a6m"),"fighter","turn_fighter",
  10.273020653865627,32.723952272022544,31.99485535959444,34.644173364843915,null,null,43.63193636269672);
 static void set(AutopilotSession s,String field,Object value)throws Exception {var f=AutopilotSession.class.getDeclaredField(field);f.setAccessible(true);f.set(s,value);}
 static AutopilotSession create(Entity e)throws Exception {AutopilotSession s=new AutopilotSession(e,profile);set(s,"phase",FlightPhase.TURN_RIGHT);set(s,"phaseTicks",100);set(s,"missionTicks",1000);set(s,"phaseTargetYaw",44f);return s;}
 static Entity plane(int id,double speed,double agl){Entity e=new Entity(new UUID(0,id),new ServerLevel());e.vel=new Vec3(0,0,speed/20.0);e.pos=new Vec3(0,100,0);e.agl=agl;e.look=new Vec3(0,0,1);return e;}
 static FlightControlOutput copy(FlightControlOutput o){return new FlightControlOutput(o.x(),o.y(),o.z(),o.engineTarget(),o.desiredDirection(),o.targetAltitude(),o.targetSpeedBps(),o.headingErrorDeg(),o.altitudeError(),o.speedErrorBps(),o.stallRisk(),o.terrainRisk(),o.reason(),o.safetyOverride());}
 public static void main(String[] args)throws Exception{
  String c=args[0];Entity e=plane(2,c.equals("prestall")?5:20,c.equals("emergency")?23:100);
  AutopilotSession s=create(e);Entity other=plane(3,20,100);AutopilotSession otherSession=create(other);
  if(c.equals("heading")||c.equals("exception"))set(s,"phaseTargetYaw",5f);
  if(c.equals("terminal"))set(s,"missionTicks",16000);
  FlightControlOutput previous=null;
  if(c.equals("previous")){previous=s.tick(null,e);if(previous!=s.lastOutput())throw new AssertionError("prior output absent");}
  if(c.equals("exception"))AutopilotLogManager.failEvent=true;
  final boolean[] innerUnknown={false};
  if(c.equals("nested")||c.equals("nestedforeign")||c.equals("nesteddirect")){
   AutopilotLogManager.hook=()->{AutopilotSession target=c.equals("nestedforeign")?otherSession:s;Entity ae=c.equals("nestedforeign")?other:e;
    if(c.equals("nesteddirect")){target.tick(null,ae);innerUnknown[0]=true;return;}
    try(PhaseTrace.Frame inner=PhaseTrace.begin(target)){FlightControlOutput v=target.tick(null,ae);inner.complete(v);innerUnknown[0]=!inner.known(target,v);}
   };
  }
  PhaseTrace.Frame f=PhaseTrace.begin(s);FlightControlOutput out=null;Throwable caught=null;
  try{
   if(c.equals("crossthread")){
    final Throwable[] workerFailure={null};Thread worker=new Thread(()->{try{s.tick(null,e);}catch(Throwable ex){workerFailure[0]=ex;}});
    worker.start();worker.join();if(workerFailure[0]!=null)throw new AssertionError("worker tick failed",workerFailure[0]);
   }
   out=(c.equals("foreigncall")?otherSession:s).tick(null,c.equals("foreigncall")?other:e);f.complete(out);
  }catch(Throwable ex){caught=ex;}
  boolean same=f.known(s,out), otherKnown=f.known(otherSession,out);
  boolean oldKnown=previous!=null&&f.known(s,previous);
  FlightControlOutput copy=out==null?null:copy(out);boolean copyKnown=copy!=null&&f.known(s,copy);
  System.out.println("CASE "+c+" same="+same+" other="+otherKnown+" previous="+oldKnown+" copy="+copyKnown+
    " valueEqual="+(out!=null&&out.equals(copy))+" frameInvalid="+f.invalid+" nestedUnknown="+innerUnknown[0]);
  System.out.println("ORIGIN entry="+f.entry+" dispatch="+f.dispatch+" afterPlan="+f.afterPlan+" terminal="+f.terminal+" emergency="+f.emergency+" exit="+f.exit);
  System.out.println("RESULT phase="+s.phase()+" phaseTicks="+s.phaseTicks()+" missionTicks="+s.missionTicks()+
    " reason="+(out==null?"null":out.reason())+" safety="+(out==null?"null":out.safetyOverride())+
    " exception="+(caught==null?"none":caught.getClass().getName()+":"+caught.getMessage()+":same="+(caught==AutopilotLogManager.FAILURE)));
  System.out.println("VALUES "+(out==null?"null":out.x()+","+out.y()+","+out.z()+","+out.engineTarget()+","+out.targetSpeedBps()));
  System.out.println("EVENTS "+AutopilotLogManager.events);System.out.println("FRAMES "+AutopilotLogManager.frames);
  f.close();boolean afterClose=f.known(s,out);System.out.println("CLOSED "+afterClose);
  if(afterClose)throw new AssertionError("closed ticket accepted");
  if(c.equals("exception")){if(caught!=AutopilotLogManager.FAILURE||same)throw new AssertionError("exception must be unknown");return;}
  if(caught!=null)throw new AssertionError("unexpected exception",caught);
  if(c.equals("crossthread")){if(same)throw new AssertionError("cross-thread session interleaving must be unknown");return;}
  if(c.equals("nested")||c.equals("nesteddirect")||c.equals("nestedforeign")){if(same||!innerUnknown[0]||(PhaseTrace.SUPPORTED&&!f.invalid))throw new AssertionError("nested must be unknown");return;}
  if(c.equals("foreigncall")){if(same||(PhaseTrace.SUPPORTED&&!f.invalid))throw new AssertionError("foreign session call must be unknown");return;}
  if(!same||otherKnown||oldKnown||copyKnown)throw new AssertionError("same call required; other, previous, equal copy unknown");
  if(c.equals("routecopy")&&!out.equals(copy))throw new AssertionError("copy control");
  if(c.equals("previous")&&(previous==out||!previous.equals(out)))throw new AssertionError("previous identity control");
  if(c.equals("heading")&&(f.dispatch!=FlightPhase.TURN_RIGHT||f.afterPlan!=FlightPhase.STALL_SETUP))throw new AssertionError("heading provenance");
  if(c.equals("prestall")&&(f.entry!=FlightPhase.TURN_RIGHT||f.dispatch!=FlightPhase.STALL_RECOVERY))throw new AssertionError("pre-stall provenance");
  if(c.equals("emergency")&&(!f.emergency||!out.safetyOverride().equals("terrain_recovery")))throw new AssertionError("emergency provenance");
  if(c.equals("terminal")&&(!f.terminal||f.dispatch!=null||f.exit!=FlightPhase.ABORTED))throw new AssertionError("terminal provenance");
 }
}'''

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mode',choices=('baseline','candidate'),required=True)
    p.add_argument('--java-home',type=Path,required=True)
    p.add_argument('--dependencies-json',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();out=a.output.absolute();out.mkdir(mode=0o700)
    fixture_path=HERE/'test_formation_recorded_turn_observation.py'
    spec=importlib.util.spec_from_file_location('prior_fixture',fixture_path)
    fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture);stubs=dict(fixture.STUBS)
    stubs['com/wwdebug/benchmark/WWDebugBenchmarkMod.java']='''package com.wwdebug.benchmark;
public class WWDebugBenchmarkMod { public static final org.slf4j.Logger LOGGER=org.slf4j.LoggerFactory.getLogger("fixture"); }'''
    log=stubs['com/wwdebug/autopilot/AutopilotLogManager.java']
    log=once(log,'public static List<String> frames=',
      'public static boolean failEvent; public static Runnable hook; public static final RuntimeException FAILURE=new IllegalStateException("fixture-sentinel"); public static List<String> frames=')
    log=once(log,'p){events.add(t+":"+r);}', 'p){if(failEvent)throw FAILURE;events.add(t+":"+r);}')
    log=once(log,'s,Entity e,JsonObject f){frames.add(f.toString());}',
      's,Entity e,JsonObject f){if(hook!=null){Runnable h=hook;hook=null;h.run();}frames.add(f.toString());}')
    stubs['com/wwdebug/autopilot/AutopilotLogManager.java']=log
    stubs['com/wwdebug/autopilot/Probe.java']=PROBE
    stubs['com/wwdebug/autopilot/PhaseTrace.java']=TRACE.replace('__SUPPORTED__',str(a.mode=='candidate').lower())
    original={n:(ROOT/(n+'.java')).read_bytes() for n in NAMES}
    session=original['AutopilotSession'].decode('utf-8')
    session=once(session,'        FlightSnapshot snapshot = FlightSnapshot.capture(aircraft);\n        missionTicks++;',
       '        PhaseTrace.entry(this,phase);\n        FlightSnapshot snapshot = FlightSnapshot.capture(aircraft);\n        missionTicks++;')
    session=once(session,'            lastOutput = terminal;\n            return terminal;',
       '            lastOutput = terminal;\n            PhaseTrace.terminal(this,phase,terminal);\n            return terminal;')
    session=once(session,'        FlightControlOutput output = plan(server, aircraft, snapshot);',
       '        PhaseTrace.dispatch(this,phase);\n        FlightControlOutput output = plan(server, aircraft, snapshot);\n        PhaseTrace.plan(this,phase,output);')
    session=once(session,'            output = control(aircraft, snapshot, output.desiredDirection(),',
       '            PhaseTrace.emergency(this);\n            output = control(aircraft, snapshot, output.desiredDirection(),')
    session=once(session,'        lastOutput = output;\n        return output;',
       '        lastOutput = output;\n        PhaseTrace.finish(this,phase,output);\n        return output;')
    deps=[Path(x) for x in json.loads(a.dependencies_json.read_text()) if not Path(x).is_dir()]
    if not deps or any(not x.is_absolute() or not x.exists() for x in deps):raise ValueError('invalid dependency archives')
    java,javac=a.java_home/'bin/java',a.java_home/'bin/javac';cp=os.pathsep.join(map(str,deps))
    inputs={str(ROOT/(n+'.java')):hashlib.sha256(original[n]).hexdigest() for n in NAMES}
    report={'base':'7d3c568ebeb876db451deb9a4c4cecda8ac05f34','mode':a.mode,'source_inputs':inputs,
      'runner_sha256':sha(Path(__file__)),'fixture_sha256':sha(fixture_path),'jdk_java_sha256':sha(java),'jdk_javac_sha256':sha(javac),
      'dependencies':{str(x):sha(x) for x in deps},'runs':{},
      'scope':'Test-only same-thread scoped identity observation; no actual arbiter, Mixin, native write, Minecraft or safety proof.'}
    shutil.copyfile(__file__,out/'runner-snapshot.py');shutil.copyfile(fixture_path,out/'fixture-snapshot.py')
    src=out/'src';classes=out/'classes';src.mkdir();classes.mkdir();paths=[]
    for n,data in original.items():
        dest=src/'prod'/(n+'.java');dest.parent.mkdir(parents=True,exist_ok=True)
        dest.write_bytes(session.encode('utf-8') if n=='AutopilotSession' and a.mode=='candidate' else data);paths.append(dest)
    for name,data in stubs.items():
        dest=src/'fixture'/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(data,encoding='utf-8');paths.append(dest)
    env={'PATH':'/usr/bin','HOME':'/nonexistent'}
    def run(label,argv):
        result=subprocess.run(argv,cwd=out,env=env,capture_output=True,text=True,timeout=30)
        (out/(label+'.stdout')).write_text(result.stdout,encoding='utf-8');(out/(label+'.stderr')).write_text(result.stderr,encoding='utf-8')
        report['runs'][label]={'argv':argv,'exit':result.returncode};print(a.mode,label,result.returncode,flush=True);return result.returncode
    rc=run('compile',[str(javac),'-encoding','UTF-8','-proc:none','--release','17','-cp',cp,
       '-sourcepath',str(out/'empty'),'-d',str(classes),*map(str,paths)])
    if rc==0:
        for case in CASES:
            run(case,[str(java),'-Xmx128m','-Xverify:all','-Xlog:class+load=info:file='+str(out/(case+'.classes.log')),
                '-cp',str(classes)+os.pathsep+cp,'com.wwdebug.autopilot.Probe',case])
    report['source_unchanged']=all(sha(ROOT/(n+'.java'))==inputs[str(ROOT/(n+'.java'))] for n in NAMES)
    report['runner_unchanged']=sha(Path(__file__))==report['runner_sha256']
    report['fixture_unchanged']=sha(fixture_path)==report['fixture_sha256']
    report['dependencies_unchanged']=all(sha(Path(k))==v for k,v in report['dependencies'].items())
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    expected={c:(1 if (a.mode=='baseline' and c in REDS) or (a.mode=='candidate' and c=='crossthread') else 0) for c in CASES}
    clean=all(report[x] for x in ('source_unchanged','runner_unchanged','fixture_unchanged','dependencies_unchanged'))
    outcomes=len(report['runs'])==len(CASES)+1 and report['runs']['compile']['exit']==0 and all(report['runs'][c]['exit']==expected[c] for c in CASES)
    # Baseline positives and candidate cross-thread counterexample are intentional reds.
    if not clean or not outcomes:return 2
    return 1

if __name__=='__main__':sys.exit(main())
