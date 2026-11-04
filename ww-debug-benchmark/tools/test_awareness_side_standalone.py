#!/usr/bin/env python3
"""Run actual awareness and mob gate against isolated fake side/scene dependencies.

No game or world is opened. Fake server/client entities deliberately share a UUID;
this models a shared map only and does not establish Minecraft logical-side sharing.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

STUBS = {
 'net/minecraft/world/level/Level.java': '''
package net.minecraft.world.level;
public class Level { public boolean isClientSide; public Level(boolean client){isClientSide=client;} }
''',
 'net/minecraft/server/level/ServerLevel.java': '''
package net.minecraft.server.level;
import net.minecraft.server.MinecraftServer; import net.minecraft.world.level.Level;
public class ServerLevel extends Level {public ServerLevel(){super(false);} public MinecraftServer getServer(){return null;}}
''',
 'net/minecraft/world/entity/Entity.java': '''
package net.minecraft.world.entity;
import java.util.UUID; import net.minecraft.world.level.Level;
public class Entity {
 public final UUID id=new UUID(0,42); public Level world; public boolean airplane=true; public LivingEntity pilot;
 public Entity(Level level){world=level;} public UUID getUUID(){return id;} public Level level(){return world;}
 public LivingEntity getControllingPassenger(){return pilot;}
}
''',
 'net/minecraft/world/entity/LivingEntity.java': '''
package net.minecraft.world.entity;
public class LivingEntity extends Entity {public LivingEntity(){super(null);}}
''',
 'net/minecraft/world/entity/Mob.java': 'package net.minecraft.world.entity; public class Mob extends LivingEntity {}',
 'net/minecraft/world/entity/player/Player.java': 'package net.minecraft.world.entity.player; public class Player extends net.minecraft.world.entity.LivingEntity {}',
 'com/wwdebug/benchmark/ReflectiveAircraft.java': '''
package com.wwdebug.benchmark;
import net.minecraft.world.entity.Entity; import com.wwdebug.autopilot.Tracker;
public class ReflectiveAircraft {public static boolean isAirplane(Entity e){Tracker.airplaneChecks++;return e.airplane;}}
''',
 'com/wwdebug/autopilot/Tracker.java': '''
package com.wwdebug.autopilot;
import java.util.*;
public class Tracker {
 public static final UUID ID=new UUID(0,42);
 public static boolean scene=true,marker=true,session=true;
 public static String update="unchanged";
 public static int airplaneChecks,statusCalls,logs;
 public static final List<String> trace=new ArrayList<>();
 public static void mark(String s){trace.add(s);}
}
''',
 'com/wwdebug/autopilot/AutonomousFlightManager.java': '''
package com.wwdebug.autopilot;
import java.util.*;
public class AutonomousFlightManager {
 public static Optional<SessionStatus> status(UUID id){Tracker.statusCalls++;return Tracker.session?Optional.of(new SessionStatus()):Optional.empty();}
 public static class SessionStatus {public FlightPhase phase(){return FlightPhase.CRUISE_OUTBOUND;}}
}
''',
 'com/wwdebug/autopilot/CombatTargetSelector.java': '''
package com.wwdebug.autopilot;
import java.util.*; import net.minecraft.server.level.ServerLevel; import net.minecraft.world.entity.Entity;
public class CombatTargetSelector {
 public static class State { }
 public static class Solution {final String value; Solution(String v){value=v;} String description(){return value;}}
 public record Update(Optional<Solution> solution,boolean acquiredOrChanged,boolean lost,String reason){}
 public static Solution current;
 public static Update update(ServerLevel level,Entity aircraft,FlightPhase phase,State state){
  Tracker.mark("selector.tick");
  return switch(Tracker.update){
   case "acquire" -> new Update(Optional.of(new Solution("new")),true,false,"new");
   case "lost" -> new Update(Optional.empty(),false,true,"lost");
   default -> new Update(Optional.of(current),false,false,"same");
  };
 }
}
''',
 'com/wwdebug/autopilot/CombatValidationSceneManager.java': '''
package com.wwdebug.autopilot;
import java.util.UUID; import net.minecraft.server.level.ServerLevel; import net.minecraft.world.entity.Entity;
public class CombatValidationSceneManager {
 public static void tick(ServerLevel l,Entity e){Tracker.mark("ground.tick");}
 public static void clear(UUID id){Tracker.mark("ground.clear");}
}
''',
 'com/wwdebug/autopilot/AirCombatValidationSceneManager.java': '''
package com.wwdebug.autopilot;
import java.util.UUID; import net.minecraft.server.level.ServerLevel; import net.minecraft.world.entity.Entity;
public class AirCombatValidationSceneManager {
 public static void tick(ServerLevel l,Entity e,FlightPhase p){Tracker.mark("air.tick");}
 public static void clear(UUID id){Tracker.mark("air.clear");}
}
''',
 'com/wwdebug/autopilot/MutualDogfightValidationManager.java': '''
package com.wwdebug.autopilot;
import java.util.UUID; import net.minecraft.server.level.ServerLevel; import net.minecraft.world.entity.Entity;
public class MutualDogfightValidationManager {
 public static void tick(ServerLevel l,Entity e,FlightPhase p){Tracker.mark("mutual.tick");}
 public static void clear(UUID id){Tracker.mark("mutual.clear");if(id.equals(Tracker.ID))Tracker.scene=false;}
}
''',
 'com/wwdebug/autopilot/MutualDogfightOpeningAdapter.java': '''
package com.wwdebug.autopilot;
import java.util.UUID; import net.minecraft.server.level.ServerLevel; import net.minecraft.world.entity.Entity;
public class MutualDogfightOpeningAdapter {
 public static void apply(ServerLevel l,Entity e,FlightPhase p){Tracker.mark("opening.apply");}
 public static void clear(UUID id){Tracker.mark("opening.clear");if(id.equals(Tracker.ID))Tracker.marker=false;}
}
''',
 'com/wwdebug/autopilot/AirCombatManeuverManager.java': '''
package com.wwdebug.autopilot;
import java.util.UUID;
public class AirCombatManeuverManager {public static void clear(UUID id){Tracker.mark("maneuver.clear");}}
''',
 'com/wwdebug/autopilot/AutopilotLogManager.java': '''
package com.wwdebug.autopilot;
import net.minecraft.server.MinecraftServer; import net.minecraft.world.entity.Entity;
public class AutopilotLogManager {
 public static void writeEvent(MinecraftServer s,Entity e,String event,String reason,FlightPhase phase){Tracker.logs++;Tracker.mark("log:"+event);}
}
''',
 'com/wwdebug/autopilot/AwarenessProbe.java': '''
package com.wwdebug.autopilot;
import java.lang.reflect.Field; import java.util.*;
import net.minecraft.world.level.Level; import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.entity.Entity; import net.minecraft.world.entity.LivingEntity; import net.minecraft.world.entity.Mob;
import net.minecraft.world.entity.player.Player;
public class AwarenessProbe {
 public static void main(String[] args)throws Exception {
  String c=args[0];boolean client=c.startsWith("client-");
  Entity e=new Entity(client?new Level(true):c.equals("server-nonserver")?new Level(false):new ServerLevel());
  Entity fakeServerOwner=new Entity(new ServerLevel());
  check(e!=fakeServerOwner && e.id.equals(fakeServerOwner.id) && e.id.equals(Tracker.ID),"fixture UUID setup");
  e.pilot=c.equals("server-player") || c.equals("client-player")?new Player():c.equals("server-empty")?null:
       c.equals("server-nonmob")?new LivingEntity():new Mob();
  if(c.equals("server-nonairplane"))e.airplane=false;
  if(c.equals("server-no-session"))Tracker.session=false;
  CombatTargetSelector.State state=new CombatTargetSelector.State();
  CombatTargetSelector.Solution solution=new CombatTargetSelector.Solution("old");
  CombatTargetSelector.current=solution;
  Map<UUID,Object> states=map("STATES"),solutions=map("SOLUTIONS");states.put(e.id,state);solutions.put(e.id,solution);
  if(c.startsWith("server-update-"))Tracker.update=c.substring("server-update-".length());
  if(c.equals("server-no-prior")){states.clear();solutions.clear();Tracker.update="acquire";}
  if(c.equals("direct-clear"))CombatAwarenessManager.clear(e.id);else CombatAwarenessManager.tick(e);
  if(client){
   check(states.get(e.id)==state && solutions.get(e.id)==solution && Tracker.scene && Tracker.marker
      && Tracker.trace.isEmpty() && Tracker.airplaneChecks==0 && Tracker.statusCalls==0 && Tracker.logs==0,
      "CONTRACT_FAIL client changed shared maps or scene/marker/manager calls: "+summary(states,solutions,e.id));
  } else if(c.equals("direct-clear") || c.equals("server-nonairplane") || c.equals("server-nonserver")
      || c.equals("server-player") || c.equals("server-empty") || c.equals("server-nonmob") || c.equals("server-no-session")){
   check(!states.containsKey(e.id) && !solutions.containsKey(e.id) && !Tracker.scene && !Tracker.marker
      && Tracker.trace.equals(List.of("ground.clear","air.clear","mutual.clear","opening.clear","maneuver.clear"))
      && Tracker.logs==0,"server/direct clear changed: "+summary(states,solutions,e.id));
  } else {
   check(Tracker.scene && Tracker.marker && Tracker.airplaneChecks==1 && Tracker.statusCalls==1,
      "valid mob admission changed: "+summary(states,solutions,e.id));
   List<String> expected=new ArrayList<>(List.of("ground.tick","air.tick","mutual.tick","opening.apply","selector.tick"));
   if(Tracker.update.equals("acquire")) expected.add("log:combat_target_acquired");
   if(Tracker.update.equals("lost")) expected.add("log:combat_target_lost");
   check(Tracker.trace.equals(expected) && states.get(e.id)!=null && (c.equals("server-no-prior") || states.get(e.id)==state),
      "awareness order or state changed: "+summary(states,solutions,e.id));
   if(Tracker.update.equals("lost"))check(!solutions.containsKey(e.id) && Tracker.logs==1,"lost target result changed");
   else if(Tracker.update.equals("acquire"))check(solutions.get(e.id)!=solution && solutions.get(e.id)!=null && Tracker.logs==1,"acquire result changed");
   else check(solutions.get(e.id)==solution && Tracker.logs==0,"unchanged target result changed");
  }
  System.out.println("PASS "+c+" "+summary(states,solutions,e.id));
 }
 @SuppressWarnings("unchecked") private static Map<UUID,Object> map(String name)throws Exception{
  Field f=CombatAwarenessManager.class.getDeclaredField(name);f.setAccessible(true);return (Map<UUID,Object>)f.get(null);
 }
 private static String summary(Map<UUID,Object> s,Map<UUID,Object> t,UUID id){return "state="+s.containsKey(id)+" solution="+t.containsKey(id)+" scene="+Tracker.scene+" marker="+Tracker.marker+" trace="+Tracker.trace+" log="+Tracker.logs;}
 private static void check(boolean ok,String message){if(!ok)throw new AssertionError(message);}
}
'''
}
CASES=('client-mob','client-player','server-nonairplane','server-nonserver','server-player','server-empty',
       'server-nonmob','server-no-session','server-update-acquire','server-update-lost','server-update-unchanged',
       'server-no-prior','direct-clear')


def sha(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for block in iter(lambda:f.read(1048576),b''):h.update(block)
 return h.hexdigest()


def inventory(paths):
 result={}
 for path in paths:
  files=sorted(f for f in path.rglob('*') if f.is_file()) if path.is_dir() else [path]
  for f in files:result[str(f)]=sha(f)
 return result


def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--java-home',type=Path,required=True)
 p.add_argument('--dependencies-json',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
 g=p.add_mutually_exclusive_group(required=True);g.add_argument('--source-root',type=Path);g.add_argument('--classes',type=Path)
 p.add_argument('--source-provenance',type=Path);a=p.parse_args()
 if a.classes and not a.source_provenance:p.error('--classes requires --source-provenance')
 out=a.output.absolute();out.mkdir(mode=0o700,parents=False,exist_ok=False)
 src=(a.source_root or a.source_provenance).resolve()
 actual=[src/'com/wwdebug/autopilot'/x for x in ('CombatAwarenessManager.java','MobPilotGate.java')]
 deps=[Path(x).resolve() for x in json.loads(a.dependencies_json.read_text())]
 java=(a.java_home/'bin/java').resolve();javac=(a.java_home/'bin/javac').resolve()
 fake=out/'fixture-classes';fake.mkdir();empty=out/'empty-sourcepath';empty.mkdir()
 production=a.classes.resolve() if a.classes else out/'production'
 if not a.classes:production.mkdir()
 fake_sources=[]
 for name,content in STUBS.items():
  path=out/'fixture-source'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(content);fake_sources.append(path)
 observed=deps+([production] if a.classes else []);inputs=actual+fake_sources+[Path(__file__).resolve(),a.dependencies_json.resolve(),java,javac]
 before={'inputs':inventory(inputs),'classpath':inventory(observed)};(out/'before.json').write_text(json.dumps(before,indent=2)+'\n')
 def run(name,argv):
  r=subprocess.run(argv,cwd=out,capture_output=True);(out/(name+'.json')).write_text(json.dumps({'argv':argv,'cwd':str(out),'exit':r.returncode},indent=2)+'\n')
  (out/(name+'.stdout')).write_bytes(r.stdout);(out/(name+'.stderr')).write_bytes(r.stderr);print(name,r.returncode,flush=True);return r.returncode
 deps_cp=os.pathsep.join(map(str,deps));failed=0
 if not a.classes:failed+=run('compile-production',[str(javac),'-proc:none','--release','17','-cp',deps_cp,'-sourcepath',str(empty),'-d',str(production),*map(str,actual)])!=0
 cp=str(production)+os.pathsep+deps_cp
 if not failed:failed+=run('compile-fixture',[str(javac),'-proc:none','--release','17','-cp',cp,'-sourcepath',str(empty),'-d',str(fake),*map(str,fake_sources)])!=0
 if not failed:
  cp=str(fake)+os.pathsep+cp
  for case in CASES:failed+=run(case,[str(java),'-Xmx128m','-Xverify:all','-Xlog:class+load=info:file='+str(out/(case+'.classes.log')),'-cp',cp,'com.wwdebug.autopilot.AwarenessProbe',case])!=0
 after={'inputs':inventory(inputs),'classpath':inventory(observed),'fixture_classes':inventory([fake]),'production_classes':inventory([production])}
 (out/'after.json').write_text(json.dumps(after,indent=2)+'\n')
 if before['inputs']!=after['inputs'] or before['classpath']!=after['classpath']:print('input changed during run',file=sys.stderr);failed+=1
 return 1 if failed else 0

if __name__=='__main__':sys.exit(main())
