#!/usr/bin/env python3
"""Actual arbiter, synthetic dependencies; no Minecraft. A red case is expected on #201."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1] / 'src/main/java/com/wwdebug/autopilot'
JAVAS = {
'net/minecraft/world/level/Level.java': '''package net.minecraft.world.level; public class Level {public boolean isClientSide; public Level(boolean c){isClientSide=c;}}''',
'net/minecraft/server/level/ServerLevel.java': '''package net.minecraft.server.level; public class ServerLevel extends net.minecraft.world.level.Level {public ServerLevel(){super(false);} public Object getServer(){return null;}}''',
'net/minecraft/world/entity/Entity.java': '''package net.minecraft.world.entity; import java.util.UUID; import net.minecraft.world.level.Level; public class Entity {public final UUID id; public final Level level; public boolean removed,player; public Entity(UUID u,Level l){id=u;level=l;} public UUID getUUID(){return id;} public Level level(){return level;} public boolean isRemoved(){return removed;}}''',
'com/wwdebug/benchmark/BenchmarkManager.java': '''package com.wwdebug.benchmark; import net.minecraft.world.entity.Entity; import com.wwdebug.autopilot.Probe; public class BenchmarkManager {public static void applyControl(Entity e){Probe.trace.add("benchmark");}}''',
'com/wwdebug/benchmark/ReflectiveAircraft.java': '''package com.wwdebug.benchmark; import net.minecraft.world.entity.Entity; import com.wwdebug.autopilot.Probe; public class ReflectiveAircraft {public static void applyControl(Entity e,float x,float y,float z,float engine){Probe.trace.add("setter:"+x+","+y+","+z+","+engine);}}''',
'com/wwdebug/autopilot/ControlProposal.java': '''package com.wwdebug.autopilot; public record ControlProposal(ControlAuthorityArbiter.Authority authority,float x,float y,float z,float engineTarget) {public boolean outranks(ControlProposal o){return o==null||authority.outranks(o.authority());}}''',
'com/wwdebug/autopilot/FlightPhase.java': '''package com.wwdebug.autopilot; public enum FlightPhase {ABORTED}''',
'com/wwdebug/autopilot/MobPilotGate.java': '''package com.wwdebug.autopilot; import net.minecraft.world.entity.Entity; public class MobPilotGate {public static boolean isPlayerControlled(Entity e){return e.player;}}''',
'com/wwdebug/autopilot/AutonomousFlightManager.java': '''package com.wwdebug.autopilot; import java.util.*; import net.minecraft.world.entity.Entity; import com.wwdebug.benchmark.ReflectiveAircraft; public class AutonomousFlightManager {public record SessionStatus(FlightPhase phase){} public static boolean session=true; public static void applyControl(Entity e){Probe.trace.add("autonomy"); if(!e.player)ReflectiveAircraft.applyControl(e,1,2,3,4);} public static Optional<SessionStatus> status(UUID id){return session?Optional.of(new SessionStatus(FlightPhase.ABORTED)):Optional.empty();}}''',
'com/wwdebug/autopilot/MutualDogfightMissionHoldAdapter.java': '''package com.wwdebug.autopilot; import net.minecraft.world.entity.Entity; public class MutualDogfightMissionHoldAdapter {public static void apply(Entity e){Probe.trace.add("hold");}}''',
'com/wwdebug/autopilot/FormationFlightManager.java': '''package com.wwdebug.autopilot; import net.minecraft.world.entity.Entity; public class FormationFlightManager {public static boolean propose; public static ControlOutcome applyControl(Entity e){Probe.trace.add("formation"); return propose ? ControlOutcome.proposed(new ControlProposal(ControlAuthorityArbiter.Authority.FORMATION,5,6,7,8)):ControlOutcome.none();}}''',
'com/wwdebug/autopilot/AirspaceSafetyProbe.java': '''package com.wwdebug.autopilot; import net.minecraft.world.entity.Entity; public class AirspaceSafetyProbe {public static boolean risk; public static boolean collisionRisk(Entity e){Probe.trace.add("risk:"+risk);return risk;}}''',
'com/wwdebug/autopilot/FighterCombatFacade.java': '''package com.wwdebug.autopilot; import net.minecraft.world.entity.Entity; public class FighterCombatFacade {public static ControlOutcome applyControl(Entity e,boolean risk){Probe.trace.add("combat:"+risk);return ControlOutcome.none();}}''',
'com/wwdebug/autopilot/TerrainAvoidancePlanner.java': '''package com.wwdebug.autopilot; import net.minecraft.world.entity.Entity; public class TerrainAvoidancePlanner {public static boolean enabled; public static boolean active(Entity e){Probe.trace.add("terrain");return enabled;}}''',
'com/wwdebug/autopilot/EnergyFighterApexYawAdapter.java': '''package com.wwdebug.autopilot; import java.util.Optional; import net.minecraft.world.entity.Entity; public class EnergyFighterApexYawAdapter {public static Optional<ControlProposal> applyControl(Entity e){Probe.trace.add("energy");return Optional.empty();}}''',
'com/wwdebug/autopilot/DefensiveAirCombatManager.java': '''package com.wwdebug.autopilot; import java.util.Optional; import net.minecraft.world.entity.Entity; public class DefensiveAirCombatManager {public static Optional<ControlProposal> applyControl(Entity e){Probe.trace.add("defensive");return Optional.empty();}}''',
'com/wwdebug/autopilot/AirCombatManeuverManager.java': '''package com.wwdebug.autopilot; import java.util.Optional; import net.minecraft.world.entity.Entity; public class AirCombatManeuverManager {public static Optional<ControlProposal> applyControl(Entity e){Probe.trace.add("offensive");return Optional.empty();}}''',
'com/wwdebug/autopilot/AutopilotLogManager.java': '''package com.wwdebug.autopilot; import net.minecraft.world.entity.Entity; public class AutopilotLogManager {public static void writeEvent(Object s,Entity e,String event,String reason,FlightPhase p){Probe.events.add(event+":"+reason);}}''',
'com/wwdebug/autopilot/Probe.java': r'''package com.wwdebug.autopilot;
import java.util.*;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.level.Level;
import net.minecraft.server.level.ServerLevel;
import static com.wwdebug.autopilot.ControlAuthorityArbiter.Authority.*;
public class Probe {
 public static final List<String> trace=new ArrayList<>(),events=new ArrayList<>();
 static void require(boolean ok,String message){if(!ok)throw new AssertionError(message);}
 static void event(int index,String fragment){require(events.get(index).contains(fragment),"unexpected event "+events);}
 static void clearTrace(){trace.clear();}
 public static void main(String[] args){
  String c=args[0]; UUID id=new UUID(0,8); Entity server=new Entity(id,new ServerLevel());
  Entity client=new Entity(new UUID(0,8),new Level(true));
  require(server!=client && server.id!=client.id && server.id.equals(client.id),"distinct objects with equal UUID values required");
  require(ControlAuthorityArbiter.applyControl(server)==BASE_AUTONOMY,"setup authority");
  require(events.size()==1,"initial event"); event(0,"from=NONE:to=BASE_AUTONOMY"); clearTrace();
  switch(c){
   case "client-removed", "client-present", "client-other-removed" -> {
    if(c.equals("client-other-removed"))client=new Entity(new UUID(0,9),new Level(true));
    client.removed=c.equals("client-removed");
    if(c.equals("client-other-removed"))client.removed=true;
    require(ControlAuthorityArbiter.applyControl(client)==NONE,"client return");
    require(trace.isEmpty(),"client triggered writer");
    require(ControlAuthorityArbiter.applyControl(server)==BASE_AUTONOMY,"server return");
    System.out.println("events="+events);System.out.println("server_trace="+trace);
    require(events.size()==1,"client must not discard server authority; got "+events);
   }
   case "client-unregistered" -> {
    Entity absent=new Entity(new UUID(0,10),new Level(true));absent.removed=true;
    require(ControlAuthorityArbiter.applyControl(absent)==NONE,"client return");
    require(trace.isEmpty(),"client triggered writer");
    Entity newServer=new Entity(absent.id,new ServerLevel());
    require(ControlAuthorityArbiter.applyControl(newServer)==BASE_AUTONOMY,"unregistered server return");
    require(events.size()==2,"unregistered first event");event(1,"from=NONE:to=BASE_AUTONOMY");
   }
   case "server-none" -> {
    AutonomousFlightManager.session=false; require(ControlAuthorityArbiter.applyControl(server)==NONE,"none return");
    require(events.size()==2,"none transition");event(1,"from=BASE_AUTONOMY:to=NONE");
    AutonomousFlightManager.session=true; ControlAuthorityArbiter.applyControl(server);
    require(events.size()==3,"none must clear cache");event(2,"from=NONE:to=BASE_AUTONOMY");
   }
   case "server-removed" -> {
    server.removed=true; ControlAuthorityArbiter.applyControl(server);require(events.size()==1,"removed must not emit");
    server.removed=false; ControlAuthorityArbiter.applyControl(server);require(events.size()==2,"removed must clear cache");event(1,"from=NONE:to=BASE_AUTONOMY");
   }
   case "player" -> {
    server.player=true; require(ControlAuthorityArbiter.applyControl(server)==PLAYER_CONTROLLED,"player return");
    require(trace.equals(List.of("autonomy","formation","energy","defensive","offensive")),"player trace="+trace);
    require(events.size()==2,"player event");event(1,"from=BASE_AUTONOMY:to=PLAYER_CONTROLLED");
   }
   case "risk-proposal", "no-risk-proposal" -> {
    FormationFlightManager.propose=true; AirspaceSafetyProbe.risk=c.equals("risk-proposal");
    var authority=ControlAuthorityArbiter.applyControl(server);
    List<String> want=new ArrayList<>(List.of("benchmark","autonomy","setter:1.0,2.0,3.0,4.0","hold","formation","risk:"+AirspaceSafetyProbe.risk,"combat:"+AirspaceSafetyProbe.risk));
    if(AirspaceSafetyProbe.risk)require(authority==COLLISION_AVOIDANCE,"risk authority");
    else {require(authority==FORMATION,"formation authority");want.add("terrain");want.add("setter:5.0,6.0,7.0,8.0");}
    require(trace.equals(want),"order or suppression changed: "+trace);
   }
   case "terrain", "risk-terrain" -> {
    TerrainAvoidancePlanner.enabled=true; FormationFlightManager.propose=true;
    AirspaceSafetyProbe.risk=c.equals("risk-terrain");
    var authority=ControlAuthorityArbiter.applyControl(server);
    var want=new ArrayList<>(List.of("benchmark","autonomy","setter:1.0,2.0,3.0,4.0","hold","formation","risk:"+AirspaceSafetyProbe.risk,"combat:"+AirspaceSafetyProbe.risk));
    if(AirspaceSafetyProbe.risk)require(authority==COLLISION_AVOIDANCE,"risk terrain authority");
    else {require(authority==TERRAIN_AVOIDANCE,"terrain authority");want.add("terrain");}
    require(trace.equals(want),"terrain order or suppression changed: "+trace);
   }
   default -> throw new IllegalArgumentException(c);
  }
  System.out.println("PASS "+c+" events="+events+" trace="+trace);
 }
}'''
}

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--java-home',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
 p.add_argument('--arbiter-source',type=Path,default=ROOT/'ControlAuthorityArbiter.java')
 a=p.parse_args(); out=a.output.absolute();out.mkdir(mode=0o700)
 src=out/'stubs';classes=out/'classes';empty=out/'empty'
 for d in (src,classes,empty):d.mkdir()
 files=[]
 for name,content in JAVAS.items():
  f=src/name;f.parent.mkdir(parents=True,exist_ok=True);f.write_text(content);files.append(f)
 actual=[a.arbiter_source.resolve(), ROOT/'ControlOutcome.java']; java=a.java_home.resolve()/'bin/java';javac=a.java_home.resolve()/'bin/javac'
 inputs=[Path(__file__).resolve(),java,javac,*actual,*files];before={str(f):sha(f) for f in inputs}
 shutil.copyfile(__file__,out/'runner-snapshot.py')
 report={'scope':'Only arbiter and ControlOutcome are actual source; all world, setter, manager, logging, session, risk and player dependencies are stand-ins. One fresh JVM per case. No real runtime or setter success is established.', 'inputs_before':before,'runner_snapshot_sha256':sha(out/'runner-snapshot.py'),'runs':{}}
 def run(name,argv):
  r=subprocess.run(argv,cwd=out,text=True,capture_output=True,timeout=30);(out/(name+'.stdout')).write_text(r.stdout);(out/(name+'.stderr')).write_text(r.stderr);report['runs'][name]={'argv':list(map(str,argv)),'exit':r.returncode};print(name,r.returncode,flush=True);return r.returncode
 rc=run('compile',[str(javac),'-proc:none','--release','17','-cp',str(empty),'-sourcepath',str(empty),'-d',str(classes),*map(str,actual),*map(str,files)])
 cases=('client-removed','client-present','client-other-removed','client-unregistered','server-none','server-removed','player','risk-proposal','no-risk-proposal','terrain','risk-terrain')
 if rc==0:
  for c in cases: run(c,[str(java),'-Xmx128m','-Xverify:all','-cp',str(classes),'com.wwdebug.autopilot.Probe',c])
 report['inputs_after']={str(f):sha(f) for f in inputs};report['inputs_unchanged']=report['inputs_before']==report['inputs_after']
 report['classes_sha256']={str(f.relative_to(classes)):sha(f) for f in sorted(classes.rglob('*.class'))}
 (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
 return 0 if report['inputs_unchanged'] and len(report['runs'])==len(cases)+1 and all(r['exit']==0 for r in report['runs'].values()) else 1
if __name__=='__main__':sys.exit(main())
