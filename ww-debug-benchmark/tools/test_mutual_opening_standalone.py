#!/usr/bin/env python3
"""Direct-call fixture for the real mutual-opening adapter; not a game or world.

A supplied classpath is used for mapped Vec3/AABB/Component. Entity, server, reflective
writes, profile and logging are deterministic stand-ins; no native setters are invoked.
Each case uses a separate JVM and a deliberately ordered synthetic candidate list.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

STUBS = {
    'net/minecraft/world/entity/Entity.java': '''
package net.minecraft.world.entity;
import java.util.*;
import net.minecraft.network.chat.Component;
import net.minecraft.world.phys.AABB;
import net.minecraft.world.phys.Vec3;
public class Entity {
 private static long nextId;
 public UUID id = new UUID(0, ++nextId);
 public net.minecraft.world.level.Level world;
 public String name = "AUTOPILOT TEST PRIMARY";
 public Set<String> tags = new HashSet<>();
 public LivingEntity pilot;
 public boolean removed, airplane = true;
 public int moves, velocities, rolls, warms, controls, stops, discards, tagRemovals;
 public Vec3 position = new Vec3(0, 0, 0), velocity = new Vec3(0, 0, 1);
 public UUID getUUID(){return id;}
 public net.minecraft.world.level.Level level(){return world;}
 public Component getName(){return Component.literal(name);}
 public Set<String> getTags(){return tags;}
 public LivingEntity getControllingPassenger(){return pilot;}
 public boolean isRemoved(){return removed;}
 public void stopRiding(){stops++;}
 public void discard(){discards++;removed=true;}
 public boolean removeTag(String tag){tagRemovals++;return tags.remove(tag);}
 public AABB getBoundingBox(){return new AABB(position.x,position.y,position.z,position.x+1,position.y+1,position.z+1);}
 public Vec3 getLookAngle(){return new Vec3(0,0,1);}
 public Vec3 getDeltaMovement(){return velocity;}
 public Vec3 position(){return position;}
 public void moveTo(double x,double y,double z,float yaw,float pitch){moves++; position=new Vec3(x,y,z);}
 public void setDeltaMovement(Vec3 v){velocities++;velocity=v;}
 public float distanceTo(Entity other){return (float) position.distanceTo(other.position);}
}
''',
    'net/minecraft/world/entity/LivingEntity.java': 'package net.minecraft.world.entity; public class LivingEntity extends Entity {}',
    'net/minecraft/world/entity/Mob.java': 'package net.minecraft.world.entity; public class Mob extends LivingEntity {}',
    'net/minecraft/world/entity/player/Player.java': 'package net.minecraft.world.entity.player; public class Player extends net.minecraft.world.entity.LivingEntity {}',
    'net/minecraft/world/level/Level.java': 'package net.minecraft.world.level; public class Level {}',
    'net/minecraft/server/level/ServerLevel.java': '''
package net.minecraft.server.level;
import java.util.*;
import java.util.function.Predicate;
import net.minecraft.server.MinecraftServer;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.phys.AABB;
public class ServerLevel extends net.minecraft.world.level.Level {
 public final List<Entity> candidates = new ArrayList<>();
 public final Map<UUID, Entity> loaded = new HashMap<>();
 public Entity getEntity(UUID uuid) { return loaded.get(uuid); }
 public List<Entity> getEntities(Entity except, AABB box, Predicate<? super Entity> filter) {
   return candidates.stream().filter(e -> e != except && box.intersects(e.getBoundingBox())).filter(filter).toList();
 }
 public MinecraftServer getServer(){return null;}
}
''',
    'com/wwdebug/benchmark/ReflectiveAircraft.java': '''
package com.wwdebug.benchmark;
import net.minecraft.world.entity.Entity;
public class ReflectiveAircraft {
 public static boolean isAirplane(Entity e){return e.airplane;}
 public static void setRoll(Entity e,float roll){e.rolls++;}
 public static void warmEngine(Entity e,float target){e.warms++;}
 public static void applyControl(Entity e,float x,float y,float z,float engine){e.controls++;}
}
''',
    'com/wwdebug/autopilot/CombatAwarenessManager.java': '''
package com.wwdebug.autopilot;
import java.util.*;
public class CombatAwarenessManager { public static Optional<Object> currentSolution(UUID id){return Optional.empty();} }
''',
    'com/wwdebug/autopilot/AirCombatManeuverManager.java': '''
package com.wwdebug.autopilot;
import net.minecraft.world.entity.Entity;
public class AirCombatManeuverManager { public static boolean active(Entity e){return false;} }
''',
    'com/wwdebug/benchmark/ReflectiveArmament.java': '''
package com.wwdebug.benchmark;
import net.minecraft.world.entity.Entity;
public class ReflectiveArmament { public static int estimatedShotsRemaining(Entity e){return 1;} }
''',
    'com/wwdebug/autopilot/AutonomousFlightManager.java': '''
package com.wwdebug.autopilot;
import java.util.*;
public class AutonomousFlightManager {
 private static final Map<UUID,Object> SESSIONS = new HashMap<>();
 public static int forceStops;
 public static void forceStop(UUID id,String reason){forceStops++;}
 private static class SessionEntry { private AutopilotSession session; }
}
''',
    'com/wwdebug/autopilot/AutopilotSession.java': '''
package com.wwdebug.autopilot;
public class AutopilotSession {
 private Object phase, phaseTicks, missionTicks, stableTicks, fallingTicks, phaseTargetYaw,
                phaseDirection, transitionReason, lastOutput;
}
''',
    'com/wwdebug/autopilot/AutopilotProfileRegistry.java': '''
package com.wwdebug.autopilot;
import java.util.Optional;
import net.minecraft.server.MinecraftServer;
import net.minecraft.world.entity.Entity;
public class AutopilotProfileRegistry {
 public static Optional<FlightProfile> resolve(MinecraftServer server, Entity e){return Optional.empty();}
}
''',
    'com/wwdebug/autopilot/FlightProfile.java': 'package com.wwdebug.autopilot; public class FlightProfile { public double cruiseSpeedBps(){return 34.0;} }',
    'com/wwdebug/autopilot/AutopilotLogManager.java': '''
package com.wwdebug.autopilot;
import net.minecraft.server.MinecraftServer;
import net.minecraft.world.entity.Entity;
public class AutopilotLogManager {
 public static int events;
 public static void writeEvent(MinecraftServer server, Entity e,String type,String detail,FlightPhase phase){events++;}
}
''',
    'com/wwdebug/autopilot/OpeningProbe.java': '''
package com.wwdebug.autopilot;
import java.lang.reflect.Field;
import java.util.*;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.Mob;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.phys.Vec3;
public class OpeningProbe {
 private static final String TAG="wwcombat:mutual_opponent";
 public static void main(String[] args) throws Exception {
  String c=args[0]; System.setProperty("wwdebug.flightGameTestScenario", "dogfight_mutual");
  if(c.startsWith("tick-")){tickCase(c);return;}
  ServerLevel level=new ServerLevel(); Entity primary=plane(level,false); Entity own=plane(level,true), decoy=plane(level,true);
  Entity actor=primary; ServerLevel callLevel=level;
  Object scene=null;
  if(!c.equals("no-scene")) {
   MutualDogfightValidationManager.tick(level,primary,FlightPhase.STARTUP);
   scene=scene(primary.id); check(scene!=null,"real manager must create scene");
   if(!c.equals("not-started")) ownScene(scene,primary,own);
  }
  level.candidates.add(own); level.loaded.put(own.id,own);
  boolean two = c.equals("decoy-before") || c.equals("two-scenes") || c.equals("player-first") || c.equals("empty-first")
       || c.equals("owner-removed") || c.equals("owner-tag-missing") || c.equals("owner-not-airplane") || c.equals("owner-outside");
  if(two) {level.candidates.add(0,decoy);level.loaded.put(decoy.id,decoy);}
  if(c.equals("two-scenes")) {
   Entity otherPrimary=plane(level,false); MutualDogfightValidationManager.tick(level,otherPrimary,FlightPhase.STARTUP);
   ownScene(scene(otherPrimary.id),otherPrimary,decoy);
  }
  if(c.equals("completed")) set(scene,"completed",true);
  if(c.equals("player") || c.equals("player-first") || c.equals("retry-player")) own.pilot=new Player();
  if(c.equals("empty") || c.equals("empty-first") || c.equals("retry-empty")) own.pilot=null;
  if(c.equals("owner-removed")) own.removed=true;
  if(c.equals("owner-tag-missing")) own.tags.clear();
  if(c.equals("owner-not-airplane")) own.airplane=false;
  if(c.equals("owner-outside")) own.position=new Vec3(500,0,0);
  if(c.equals("owner-unloaded") || c.equals("late-lookup")) level.loaded.remove(own.id);
  if(c.equals("wrong-uuid")) set(scene,"opponentUuid",decoy.id);
  if(c.equals("different-primary")) {actor=plane(level,false);actor.id=primary.id;}
  if(c.equals("primary-other-world")) primary.world=new ServerLevel();
  if(c.equals("opponent-other-world")) own.world=new ServerLevel();
  if(c.equals("different-level")) {
   callLevel=new ServerLevel();callLevel.candidates.add(own);callLevel.loaded.put(own.id,own);
  }
  if(c.equals("same-uuid-other-object")) {
   decoy.id=own.id;level.loaded.put(decoy.id,decoy);level.candidates.clear();level.candidates.add(decoy);
  }
  if(c.equals("reload")) {
   own.removed=true;decoy.id=own.id;level.loaded.put(decoy.id,decoy);level.candidates.clear();level.candidates.add(decoy);
   MutualDogfightValidationManager.tick(level,primary,FlightPhase.STARTUP);
   check(get(scene,"opponent")==decoy,"real manager did not rebind reloaded object");
  }
  if(c.equals("wrong-scenario")) System.setProperty("wwdebug.flightGameTestScenario", "full");
  if(c.equals("wrong-name")) primary.name="ordinary";
  if(c.equals("tagged-primary")) primary.tags.add(TAG);
  if(c.equals("no-candidate")) level.candidates.clear();
  MutualDogfightOpeningAdapter.apply(callLevel,actor,FlightPhase.CRUISE_OUTBOUND);
  boolean noAction=Set.of("player","empty","player-first","empty-first","retry-player","retry-empty",
   "wrong-scenario","wrong-name","tagged-primary","no-candidate","no-scene","not-started","completed",
   "owner-removed","owner-tag-missing","owner-not-airplane","owner-outside","owner-unloaded","late-lookup",
   "wrong-uuid","different-primary","different-level","primary-other-world","opponent-other-world",
   "same-uuid-other-object").contains(c);
  if(noAction) {
   check(writes(own)==0 && writes(decoy)==0,"CONTRACT_FAIL unexpected mutation own="+describe(own)+" decoy="+describe(decoy));
   check(!applied(primary.id) && AutopilotLogManager.events==0,"refusal must not mark APPLIED or log success");
  } else {
   Entity expected=c.equals("reload")?decoy:own;Entity other=expected==own?decoy:own;
   positive(expected,other);check(applied(primary.id) && AutopilotLogManager.events==1,"missing success state");
   MutualDogfightOpeningAdapter.apply(callLevel,actor,FlightPhase.CRUISE_OUTBOUND);
   positive(expected,other);check(AutopilotLogManager.events==1,"duplicate opening");
  }
  if(c.startsWith("retry-") || c.equals("late-lookup")) {
   own.pilot=new Mob();level.loaded.put(own.id,own);
   MutualDogfightOpeningAdapter.apply(level,primary,FlightPhase.CRUISE_OUTBOUND);
   positive(own,decoy);check(applied(primary.id) && AutopilotLogManager.events==1,"same owner retry failed");
  }
  System.out.println("PASS "+c+" own="+describe(own)+" decoy="+describe(decoy)+" applied="+applied(primary.id)+" events="+AutopilotLogManager.events);
 }
 private static void tickCase(String c)throws Exception {
  ServerLevel level=new ServerLevel(), otherLevel=new ServerLevel();
  Entity primary=plane(level,false), opponent=plane(level,true), actor=primary;
  boolean noScene=c.equals("tick-mismatch-before-create");
  if(noScene) {
   MutualDogfightValidationManager.tick(otherLevel,primary,FlightPhase.STARTUP);
   check(scene(primary.id)==null && allActions(primary,opponent)==0 && AutopilotLogManager.events==0
         && AutonomousFlightManager.forceStops==0,"CONTRACT_FAIL level mismatch created a scene or wrote state");
   System.out.println("PASS "+c);return;
  }
  MutualDogfightValidationManager.tick(level,primary,FlightPhase.STARTUP);
  Object state=scene(primary.id);check(state!=null,"real manager must create scene");ownScene(state,primary,opponent);
  boolean completing=c.endsWith("-completion");
  if(completing){set(state,"primaryInitialShots",2);set(state,"opponentInitialShots",2);}
  ServerLevel callLevel=level;
  if(c.startsWith("tick-different-object")){actor=plane(level,false);actor.id=primary.id;}
  if(c.startsWith("tick-different-both")){actor=plane(otherLevel,false);actor.id=primary.id;callLevel=otherLevel;}
  if(c.startsWith("tick-moved-owner")){primary.world=otherLevel;callLevel=otherLevel;}
  if(c.startsWith("tick-wrong-level")){callLevel=otherLevel;}
  Map<String,Object> before=snapshot(state);int actionsBefore=allActions(primary,opponent)+allActions(actor,null);
  MutualDogfightValidationManager.tick(callLevel,actor,FlightPhase.STARTUP);
  boolean own=c.startsWith("tick-own-");
  if(!own){
   check(snapshot(state).equals(before) && scene(primary.id)==state,"CONTRACT_FAIL non-owner changed scene state forceStops="+AutonomousFlightManager.forceStops
     +" opponentDiscard="+opponent.discards+" pilotStop="+opponent.pilot.stops+" pilotDiscard="+opponent.pilot.discards
     +" tagRemovals="+(actor.tagRemovals+actor.pilot.tagRemovals)+" events="+AutopilotLogManager.events);
   check(allActions(primary,opponent)+allActions(actor,null)==actionsBefore && AutopilotLogManager.events==0
         && AutonomousFlightManager.forceStops==0,"CONTRACT_FAIL non-owner invoked a writer, log, or cleanup");
  } else if(completing) {
   check(Boolean.TRUE.equals(get(state,"completed")) && AutonomousFlightManager.forceStops==1
      && opponent.pilot.stops==1 && opponent.pilot.discards==1 && opponent.discards==1
      && primary.tagRemovals==2 && primary.pilot.tagRemovals==2 && AutopilotLogManager.events==1,
      "valid owner completion must reach fake cleanup and event");
  } else {
   check(((Integer)get(state,"ageTicks"))==1 && !Boolean.TRUE.equals(get(state,"completed"))
      && allActions(primary,opponent)==0 && AutonomousFlightManager.forceStops==0 && AutopilotLogManager.events==0,
      "valid owner tick must advance without cleanup");
  }
  System.out.println("PASS "+c+" age="+get(state,"ageTicks")+" completed="+get(state,"completed")
    +" forceStops="+AutonomousFlightManager.forceStops+" opponentDiscard="+opponent.discards+" events="+AutopilotLogManager.events);
 }
 private static int allActions(Entity first,Entity second){return actions(first)+(first.pilot==null?0:actions(first.pilot))
       +(second==null?0:actions(second)+(second.pilot==null?0:actions(second.pilot)));}
 private static int actions(Entity e){return writes(e)+e.stops+e.discards+e.tagRemovals;}
 private static Map<String,Object> snapshot(Object state)throws Exception{
  Map<String,Object> out=new HashMap<>();for(Field f:state.getClass().getDeclaredFields()){
   if(!java.lang.reflect.Modifier.isStatic(f.getModifiers())){f.setAccessible(true);out.put(f.getName(),f.get(state));}}
  return out;
 }
 private static Entity plane(ServerLevel l,boolean tag){Entity e=new Entity();e.world=l;e.pilot=new Mob();if(tag)e.tags.add(TAG);return e;}
 private static void ownScene(Object scene,Entity primary,Entity opponent)throws Exception{
  set(scene,"started",true);set(scene,"opponent",opponent);set(scene,"opponentUuid",opponent.id);
  set(scene,"primaryPilotUuid",primary.pilot.id);set(scene,"opponentPilotUuid",opponent.pilot.id);
 }
 @SuppressWarnings("unchecked") private static Object scene(UUID id)throws Exception{
  Field f=MutualDogfightValidationManager.class.getDeclaredField("SCENES");f.setAccessible(true);return ((Map<UUID,Object>)f.get(null)).get(id);
 }
 private static Object get(Object o,String name)throws Exception{Field f=o.getClass().getDeclaredField(name);f.setAccessible(true);return f.get(o);}
 private static void set(Object o,String name,Object value)throws Exception{Field f=o.getClass().getDeclaredField(name);f.setAccessible(true);f.set(o,value);}
 private static int writes(Entity e){return e.moves+e.velocities+e.rolls+e.warms+e.controls;}
 private static String describe(Entity e){return e.moves+"/"+e.velocities+"/"+e.rolls+"/"+e.warms+"/"+e.controls;}
 private static void positive(Entity e,Entity other){check(e.moves==1 && e.velocities==1 && e.rolls==1 && e.warms==1 && e.controls==1 && writes(other)==0,"wrong selected entity own="+describe(e)+" other="+describe(other));}
 @SuppressWarnings("unchecked") private static boolean applied(UUID id)throws Exception{
  Field field=MutualDogfightOpeningAdapter.class.getDeclaredField("APPLIED");field.setAccessible(true);return ((Set<UUID>)field.get(null)).contains(id);
 }
 private static void check(boolean ok,String reason){if(!ok)throw new AssertionError(reason);}
}
'''
}
CASES = ('player','empty','player-first','empty-first','retry-player','retry-empty','mob',
         'wrong-scenario','wrong-name','tagged-primary','no-candidate','no-scene','not-started','completed',
         'owner-removed','owner-tag-missing','owner-not-airplane','owner-outside','owner-unloaded','late-lookup',
         'wrong-uuid','different-primary','different-level','primary-other-world','opponent-other-world',
         'same-uuid-other-object','decoy-before','two-scenes','reload',
         'tick-mismatch-before-create','tick-different-object-normal','tick-different-object-completion',
         'tick-different-both-normal','tick-different-both-completion','tick-moved-owner-normal',
         'tick-moved-owner-completion','tick-wrong-level-normal','tick-wrong-level-completion',
         'tick-own-normal','tick-own-completion')


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1048576),b''): h.update(block)
    return h.hexdigest()


def inventory(paths):
    result={}
    for path in paths:
        files=sorted(f for f in path.rglob('*') if f.is_file()) if path.is_dir() else [path]
        for f in files: result[str(f)]=sha(f)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--java-home',type=Path,required=True)
    p.add_argument('--dependencies-json',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    g=p.add_mutually_exclusive_group(required=True)
    g.add_argument('--source-root',type=Path)
    g.add_argument('--classes',type=Path)
    p.add_argument('--source-provenance',type=Path)
    a=p.parse_args()
    if a.classes and not a.source_provenance: p.error('--classes requires --source-provenance')
    out=a.output.absolute();out.mkdir(mode=0o700,parents=False,exist_ok=False)
    src=(a.source_root or a.source_provenance).resolve()
    actual=[src/'com/wwdebug/autopilot'/name for name in ('MutualDogfightOpeningAdapter.java','MobPilotGate.java','MutualDogfightValidationManager.java')]
    deps=[Path(x).resolve() for x in json.loads(a.dependencies_json.read_text())]
    java=(a.java_home/'bin/java').resolve();javac=(a.java_home/'bin/javac').resolve()
    output=out/'fixture-classes';output.mkdir();empty=out/'empty-sourcepath';empty.mkdir()
    production=a.classes.resolve() if a.classes else out/'production'
    if not a.classes: production.mkdir()
    fake_sources=[]
    for name,content in STUBS.items():
        path=out/'fixture-source'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(content);fake_sources.append(path)
    observed=deps+([a.classes.resolve()] if a.classes else [])
    inputfiles=actual+fake_sources+[Path(__file__).resolve(),a.dependencies_json.resolve(),java,javac]
    before={'inputs':inventory(inputfiles),'classpath':inventory(observed)}
    (out/'before.json').write_text(json.dumps(before,indent=2)+'\n')
    def run(name,argv):
        r=subprocess.run(argv,cwd=out,capture_output=True)
        (out/(name+'.json')).write_text(json.dumps({'argv':argv,'cwd':str(out),'exit':r.returncode},indent=2)+'\n')
        (out/(name+'.stdout')).write_bytes(r.stdout);(out/(name+'.stderr')).write_bytes(r.stderr)
        print(name,r.returncode,flush=True);return r.returncode
    deps_cp=os.pathsep.join(map(str,deps))
    failed=0
    if not a.classes:
        failed+=run('compile-production',[str(javac),'-proc:none','--release','17','-cp',deps_cp,'-sourcepath',str(empty),'-d',str(production),*map(str,actual)]) != 0
    cp=str(production)+os.pathsep+deps_cp
    if not failed:
        failed+=run('compile-fixture',[str(javac),'-proc:none','--release','17','-cp',cp,'-sourcepath',str(empty),'-d',str(output),*map(str,fake_sources)]) != 0
    if not failed:
        cp=str(output)+os.pathsep+cp
        for case in CASES:
            failed+=run(case,[str(java),'-Xmx128m','-Xverify:all','-Xlog:class+load=info:file='+str(out/(case+'.classes.log')),'-cp',cp,'com.wwdebug.autopilot.OpeningProbe',case]) != 0
    after={'inputs':inventory(inputfiles),'classpath':inventory(observed),'fixture_classes':inventory([output]),'production_classes':inventory([production])}
    (out/'after.json').write_text(json.dumps(after,indent=2)+'\n')
    if before['inputs']!=after['inputs'] or before['classpath']!=after['classpath']:
        print('input changed during run',file=sys.stderr);failed+=1
    return 1 if failed else 0

if __name__=='__main__':sys.exit(main())
