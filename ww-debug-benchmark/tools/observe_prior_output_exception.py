#!/usr/bin/env python3
"""Compare a prior-output session after an injected second-tick exception.

Private source copies and fakes only. No reentry, native setter or Minecraft.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys

HERE=Path(__file__).resolve().parent
BASE=HERE/'observe_session_phase_origin.py'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

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
  String c=args[0];boolean traced=Boolean.parseBoolean(args[1]);
  Entity e=new Entity(new UUID(0,2),new ServerLevel());e.vel=new Vec3(0,0,1.0);e.pos=new Vec3(0,100,0);
  e.agl=100.0;e.look=new Vec3(0,0,1);e.yaw=0;e.pitch=0;
  AutopilotSession session=new AutopilotSession(e,profile);
  set(session,"phase",FlightPhase.TURN_RIGHT);set(session,"phaseTicks",100);set(session,"missionTicks",1000);set(session,"phaseTargetYaw",44f);
  FlightControlOutput prior=session.tick(null,e);
  if(session.lastOutput()!=prior||session.phase()!=FlightPhase.TURN_RIGHT||session.phaseTicks()!=101||AutopilotLogManager.frames.size()!=1)throw new AssertionError("first tick did not establish prior output");
  System.out.println("PRIOR phase="+session.phase()+" phaseTicks="+session.phaseTicks()+" missionTicks="+session.missionTicks()+" output="+fmt(prior));
  PhaseTrace.reset(); // Clears only the artificial observer, never the session.
  if(c.equals("eventexception")){set(session,"phaseTargetYaw",5f);AutopilotLogManager.failEvent=true;}
  else if(c.equals("frameexception"))AutopilotLogManager.failFrame=true;
  else if(!c.equals("success"))throw new IllegalArgumentException(c);
  FlightControlOutput result=null;Throwable thrown=null;
  try{result=session.tick(null,e);}catch(Throwable ex){thrown=ex;}
  System.out.println("CASE "+c);
  System.out.println("STATE phase="+session.phase()+" phaseTicks="+session.phaseTicks()+" missionTicks="+session.missionTicks()+" transition="+session.transitionReason());
  System.out.println("OUTPUT "+fmt(result));System.out.println("LAST "+fmt(session.lastOutput()));
  System.out.println("IDENTITY lastIsPrior="+(session.lastOutput()==prior)+" lastIsResult="+(result!=null&&session.lastOutput()==result));
  System.out.println("EVENTS "+AutopilotLogManager.events);System.out.println("FRAMES "+AutopilotLogManager.frames);
  System.out.println("THROWN "+(thrown==null?"none":thrown.getClass().getName()+":"+thrown.getMessage()+":same="+(thrown==AutopilotLogManager.FAILURE)));
  if(traced)System.out.println("TRACE entry="+PhaseTrace.entry+" dispatch="+PhaseTrace.dispatch+" afterPlan="+PhaseTrace.afterPlan+
    " terminal="+PhaseTrace.terminal+" emergency="+PhaseTrace.emergency+" exit="+PhaseTrace.exit+
    " planned="+fmt(PhaseTrace.planOutput)+" returned="+fmt(PhaseTrace.output));
  if(c.equals("success")){
   if(thrown!=null||result==null||session.lastOutput()!=result||session.lastOutput()==prior||session.phase()!=FlightPhase.TURN_RIGHT||session.phaseTicks()!=102||session.missionTicks()!=1002||AutopilotLogManager.frames.size()!=2)throw new AssertionError("second success");
  }else{
   if(thrown!=AutopilotLogManager.FAILURE||result!=null||session.lastOutput()!=prior||session.missionTicks()!=1002||AutopilotLogManager.frames.size()!=1)throw new AssertionError("expected prior output after exception");
   if(c.equals("eventexception")&&(session.phase()!=FlightPhase.STALL_SETUP||session.phaseTicks()!=0||!session.transitionReason().equals("right_turn_heading_reached")))throw new AssertionError("event failure state");
   if(c.equals("frameexception")&&(session.phase()!=FlightPhase.TURN_RIGHT||session.phaseTicks()!=102))throw new AssertionError("frame failure state");
  }
  if(traced){
   if(PhaseTrace.entry!=FlightPhase.TURN_RIGHT||PhaseTrace.dispatch!=FlightPhase.TURN_RIGHT)throw new AssertionError("missing same tick entry/dispatch");
   if(c.equals("eventexception")&&(PhaseTrace.afterPlan!=null||PhaseTrace.output!=null))throw new AssertionError("event failed before plan return");
   if(c.equals("frameexception")&&(PhaseTrace.afterPlan!=FlightPhase.TURN_RIGHT||PhaseTrace.planOutput==null||PhaseTrace.output!=null))throw new AssertionError("frame failed after plan return");
   if(c.equals("success")&&(PhaseTrace.afterPlan!=FlightPhase.TURN_RIGHT||PhaseTrace.output!=result))throw new AssertionError("successful trace");
  }
 }
}'''

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--java-home',type=Path,required=True)
    parser.add_argument('--dependencies-json',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    wrapper_before=sha(Path(__file__));base_before=sha(BASE)
    spec=importlib.util.spec_from_file_location('phase_origin',BASE)
    base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
    marker=' static void entry(FlightPhase p){entry=p;}'
    if base.TRACE.count(marker)!=1:raise ValueError('trace marker changed')
    base.TRACE=base.TRACE.replace(marker,''' static void reset(){entry=null;dispatch=null;afterPlan=null;exit=null;planOutput=null;output=null;terminal=false;emergency=false;}
'''+marker,1)
    base.PROBE=PROBE;base.CASES=['success','eventexception','frameexception']
    rc=base.main()
    out=args.output.absolute()
    manifest={'wrapper_before':wrapper_before,'wrapper_after':sha(Path(__file__)),
              'base_runner_before':base_before,'base_runner_after':sha(BASE),
              'base_report_sha256':sha(out/'report.json'),'base_exit':rc,
              'scope':'Two artificial direct session ticks, logger sentinel on second; no reentry, Mixin, real world or setter.'}
    shutil.copyfile(__file__,out/'prior-runner-snapshot.py')
    manifest['wrapper_snapshot_sha256']=sha(out/'prior-runner-snapshot.py')
    with (out/'prior-wrapper-manifest.json').open('x',encoding='utf-8') as f:json.dump(manifest,f,indent=2);f.write('\n')
    return 0 if rc==0 and manifest['wrapper_before']==manifest['wrapper_after']==manifest['wrapper_snapshot_sha256'] and manifest['base_runner_before']==manifest['base_runner_after'] else 1

if __name__=='__main__':sys.exit(main())
