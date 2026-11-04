#!/usr/bin/env python3
"""Exercise the unchanged scene manager using disposable Java stand-ins, never a world.

Each Java process starts from an isolated synthetic scene.  This deliberately invokes the
real package-private clear method or private completion method, with reflective setup of the
otherwise private scene.  It does not prove Minecraft mounting, world reload or tick behavior.
"""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys


STUBS = {
    "net/minecraft/network/chat/Component.java": '''
package net.minecraft.network.chat;
public final class Component {
 private final String text; private Component(String value) { text=value; }
 public static Component literal(String value) { return new Component(value); }
 public String getString() { return text; }
}
''',
    "net/minecraft/resources/ResourceLocation.java": '''
package net.minecraft.resources;
public final class ResourceLocation { public ResourceLocation(String namespace,String name) {} }
''',
    "net/minecraft/server/MinecraftServer.java": '''
package net.minecraft.server; public final class MinecraftServer {}
''',
    "net/minecraft/world/phys/Vec3.java": '''
package net.minecraft.world.phys;
public final class Vec3 {
 public final double x,y,z; public Vec3(double a,double b,double c){x=a;y=b;z=c;}
 public double lengthSqr(){return x*x+y*y+z*z;} public Vec3 normalize(){return this;}
 public Vec3 scale(double n){return new Vec3(x*n,y*n,z*n);}
 public Vec3 add(double a,double b,double c){return new Vec3(x+a,y+b,z+c);}
 public Vec3 add(Vec3 v){return add(v.x,v.y,v.z);}
 public Vec3 subtract(Vec3 v){return add(-v.x,-v.y,-v.z);}
}
''',
    "net/minecraft/server/level/ServerLevel.java": '''
package net.minecraft.server.level;
import java.util.*; import net.minecraft.server.MinecraftServer; import net.minecraft.world.entity.Entity;
public final class ServerLevel {
 public final Map<UUID,Entity> entities=new HashMap<>();
 private final MinecraftServer server=new MinecraftServer();
 public MinecraftServer getServer(){return server;}
 public Entity getEntity(UUID id){return entities.get(id);}
 public boolean addFreshEntity(Entity e){entities.put(e.getUUID(),e); return true;}
}
''',
    "net/minecraft/world/entity/Entity.java": '''
package net.minecraft.world.entity;
import java.util.*; import net.minecraft.network.chat.Component;
import net.minecraft.server.level.ServerLevel; import net.minecraft.world.phys.Vec3;
public class Entity {
 public final UUID id; public final ServerLevel world; public Entity pilot;
 public final List<Entity> passengers=new ArrayList<>();
 public boolean removed; public int discards,stops,tagRemovals; public final Set<String> tags=new HashSet<>();
 public Entity(ServerLevel w,UUID u){world=w;id=u;}
 public UUID getUUID(){return id;} public ServerLevel level(){return world;}
 public Entity getControllingPassenger(){return pilot;}
 public void setPilot(Entity p){passengers.clear();pilot=p;if(p!=null)passengers.add(p);}
 public void addPassenger(Entity p){passengers.add(p);}
 public void discard(){discards++;removed=true;} public void stopRiding(){stops++;}
 public boolean isRemoved(){return removed;} public Set<String> getTags(){return tags;}
 public void addTag(String s){tags.add(s);} public void removeTag(String s){tagRemovals++;tags.remove(s);}
 public Component getName(){return Component.literal("AUTOPILOT TEST PRIMARY");}
 public void setCustomName(Component c){} public void setCustomNameVisible(boolean v){}
 public void setInvulnerable(boolean v){} public void moveTo(double x,double y,double z,float yaw,float pitch){}
 public Vec3 getLookAngle(){return new Vec3(0,0,1);} public Vec3 getDeltaMovement(){return new Vec3(0,0,1);}
 public Vec3 position(){return new Vec3(0,0,0);} public double distanceTo(Entity e){return 10;}
 public void setDeltaMovement(Vec3 v){} public float getYRot(){return 0;}
}
''',
    "net/minecraft/world/entity/player/Player.java": '''
package net.minecraft.world.entity.player;
import java.util.UUID; import net.minecraft.server.level.ServerLevel; import net.minecraft.world.entity.Entity;
public final class Player extends Entity { public Player(ServerLevel w,UUID id){super(w,id);} }
''',
    "net/minecraft/world/entity/Mob.java": '''
package net.minecraft.world.entity;
import java.util.UUID; import net.minecraft.server.level.ServerLevel;
public class Mob extends Entity { public Mob(ServerLevel w,UUID id){super(w,id);} }
''',
    "net/minecraft/world/entity/npc/Villager.java": '''
package net.minecraft.world.entity.npc;
import java.util.UUID; import net.minecraft.server.level.ServerLevel; import net.minecraft.world.entity.Entity; import net.minecraft.world.entity.Mob;
public final class Villager extends Mob {
 public Villager(ServerLevel w,UUID id){super(w,id);} public void setNoAi(boolean b){} public void setSilent(boolean b){}
 public boolean startRiding(Entity e,boolean force){e.setPilot(this);return true;}
}
''',
    "net/minecraft/world/entity/EntityType.java": '''
package net.minecraft.world.entity;
import java.util.UUID; import net.minecraft.server.level.ServerLevel; import net.minecraft.world.entity.npc.Villager;
public class EntityType<T extends Entity> {
 public static final EntityType<Villager> VILLAGER=new EntityType<>();
 @SuppressWarnings("unchecked") public T create(ServerLevel l){return (T)new Villager(l,UUID.randomUUID());}
}
''',
    "net/minecraftforge/registries/ForgeRegistries.java": '''
package net.minecraftforge.registries;
import net.minecraft.resources.ResourceLocation; import net.minecraft.world.entity.EntityType;
public final class ForgeRegistries {
 public static final Registry ENTITY_TYPES=new Registry();
 public static final class Registry { public EntityType<?> getValue(ResourceLocation k){return new EntityType<>();} }
}
''',
    "com/wwdebug/benchmark/ReflectiveAircraft.java": '''
package com.wwdebug.benchmark; import net.minecraft.world.entity.Entity;
public final class ReflectiveAircraft {
 public static void fillFuel(Entity e){} public static void warmEngine(Entity e,float f){}
 public static void applyControl(Entity e,float x,float y,float z,float engine){}
}
''',
    "com/wwdebug/benchmark/ReflectiveArmament.java": '''
package com.wwdebug.benchmark; import net.minecraft.world.entity.Entity;
public final class ReflectiveArmament {
 public static boolean equipTestMachineGun(Entity e,int n){return true;}
 public static int estimatedShotsRemaining(Entity e){return 48;}
}
''',
    "com/wwdebug/autopilot/FlightPhase.java": '''
package com.wwdebug.autopilot; public enum FlightPhase { CRUISE_OUTBOUND }
''',
    "com/wwdebug/autopilot/AutopilotSession.java": '''
package com.wwdebug.autopilot; import net.minecraft.world.phys.Vec3;
final class AutopilotSession {
 FlightPhase phase; int phaseTicks,missionTicks,stableTicks,fallingTicks;
 float phaseTargetYaw; Vec3 phaseDirection; String transitionReason; Object lastOutput;
}
''',
    "com/wwdebug/autopilot/AutonomousFlightManager.java": '''
package com.wwdebug.autopilot;
import java.util.*; import net.minecraft.world.entity.Entity;
public final class AutonomousFlightManager {
 private static final Map<UUID,SessionEntry> SESSIONS=new HashMap<>();
 private static final class SessionEntry { final AutopilotSession session=new AutopilotSession(); }
 public static int forceStops; public static UUID stoppedUuid;
 public static void forceStop(UUID id,String reason){forceStops++;stoppedUuid=id;}
 public static void applyControl(Entity e){SESSIONS.put(e.getUUID(),new SessionEntry());}
 public static Optional<SessionStatus> status(UUID id){return Optional.empty();}
 public record SessionStatus(FlightPhase phase){}
}
''',
    "com/wwdebug/autopilot/AutopilotProfileRegistry.java": '''
package com.wwdebug.autopilot;
import java.util.Optional; import net.minecraft.server.MinecraftServer; import net.minecraft.world.entity.Entity;
final class AutopilotProfileRegistry {
 static Optional<Profile> resolve(MinecraftServer s,Entity a){return Optional.empty();}
 record Profile(double cruiseSpeedBps){}
}
''',
    "com/wwdebug/autopilot/CombatAwarenessManager.java": '''
package com.wwdebug.autopilot; import java.util.*;
final class CombatAwarenessManager {
 static Optional<Solution> currentSolution(UUID u){return Optional.empty();}
 record Solution(UUID targetUuid){}
}
''',
    "com/wwdebug/autopilot/AirCombatManeuverManager.java": '''
package com.wwdebug.autopilot; import net.minecraft.world.entity.Entity;
final class AirCombatManeuverManager { static boolean active(Entity e){return false;} }
''',
    "com/wwdebug/autopilot/AutopilotLogManager.java": '''
package com.wwdebug.autopilot; import net.minecraft.server.MinecraftServer; import net.minecraft.world.entity.Entity;
final class AutopilotLogManager {
 static int completions; static String lastEvent="";
 static void writeEvent(MinecraftServer s,Entity e,String event,String reason,FlightPhase phase){
  lastEvent=event; if(event.equals("mutual_dogfight_validation_completed"))completions++;
 }
}
''',
    "com/wwdebug/autopilot/MutualCleanupProbe.java": '''
package com.wwdebug.autopilot;
import java.lang.reflect.*; import java.util.*;
import net.minecraft.server.level.ServerLevel; import net.minecraft.world.entity.Entity; import net.minecraft.world.entity.Mob;
import net.minecraft.world.entity.player.Player;
public final class MutualCleanupProbe {
 private static final String RED="wwcombat:faction:red", HOSTILE="wwcombat:hostile:blue";
 private static final UUID PRIMARY=new UUID(0,1), OPPONENT=new UUID(0,2), OLD_PILOT=new UUID(0,3);
 private static void check(boolean ok,String message){if(!ok)throw new AssertionError(message);}
 @SuppressWarnings("unchecked") public static void main(String[] args)throws Exception {
  String test=args[0]; ServerLevel level=new ServerLevel(); ServerLevel other=new ServerLevel();
  Entity primary=new Entity(level,PRIMARY), opponent=new Entity(level,OPPONENT), oldPilot=new Mob(level,OLD_PILOT);
  Entity otherPilot=test.equals("player") ? new Player(level,new UUID(0,4)) : new Mob(level,new UUID(0,4));
  Entity primaryPilot=new Mob(level,new UUID(0,5));
  primary.setPilot(primaryPilot); primary.addTag(RED); primary.addTag(HOSTILE);
  primaryPilot.addTag(RED); primaryPilot.addTag(HOSTILE);
  opponent.setPilot(oldPilot); level.addFreshEntity(primary); level.addFreshEntity(opponent); level.addFreshEntity(oldPilot);
  Class<?> sceneClass=Class.forName("com.wwdebug.autopilot.MutualDogfightValidationManager$Scene");
  Constructor<?> ctor=sceneClass.getDeclaredConstructor(ServerLevel.class,Entity.class);ctor.setAccessible(true);
  Object scene=ctor.newInstance(level,primary);
  set(scene,"started",true);set(scene,"primaryPilotUuid",primaryPilot.getUUID());
  set(scene,"opponent",opponent);set(scene,"opponentUuid",opponent.getUUID());set(scene,"opponentPilotUuid",oldPilot.getUUID());
  Field mapField=MutualDogfightValidationManager.class.getDeclaredField("SCENES");mapField.setAccessible(true);
  Map<UUID,Object> scenes=(Map<UUID,Object>)mapField.get(null);scenes.put(primary.getUUID(),scene);
  if(test.equals("player")||test.equals("other-mob"))opponent.setPilot(otherPilot);
  if(test.equals("empty-seat"))opponent.setPilot(null);
  if(test.equals("additional-player")){
   otherPilot=new Player(level,new UUID(0,4));opponent.addPassenger(otherPilot);
  }
  if(test.equals("primary-player"))primary.setPilot(new Player(level,new UUID(0,7)));
  if(test.equals("partial")){
   set(scene,"started",false);set(scene,"opponent",null);set(scene,"opponentUuid",null);
   set(scene,"opponentPilotUuid",null);set(scene,"primaryPilotUuid",null);
  }
  Entity replacement=null;
  if(test.equals("reloaded-other-instance")){
   opponent.removed=true; replacement=new Entity(level,OPPONENT);replacement.setPilot(otherPilot);
   level.addFreshEntity(replacement);
  }
  if(test.equals("complete-player")){
   Player replacementPilot=new Player(level,new UUID(0,6));replacementPilot.addTag(RED);replacementPilot.addTag(HOSTILE);
   primary.setPilot(replacementPilot);otherPilot=replacementPilot;
  }
  if(test.equals("unregistered"))scenes.clear();
  if(test.equals("complete-player")||test.equals("preexisting-tags")||test.equals("reloaded-other-instance")){
   Method m=MutualDogfightValidationManager.class.getDeclaredMethod("completeScene",ServerLevel.class,Entity.class,sceneClass,FlightPhase.class,String.class);
   m.setAccessible(true);m.invoke(null,level,primary,scene,FlightPhase.CRUISE_OUTBOUND,"synthetic");
  } else {
   UUID caller=test.equals("same-uuid-other-instance")?new Entity(other,PRIMARY).getUUID():primary.getUUID();
   MutualDogfightValidationManager.clear(caller);
  }
  System.out.println("OBSERVED case="+test+" scene="+scenes.containsKey(PRIMARY)
    +" forceStops="+AutonomousFlightManager.forceStops+" opponentDiscards="+opponent.discards
    +" oldPilotDiscards="+oldPilot.discards+" currentStops="+otherPilot.stops+" currentDiscards="+otherPilot.discards
    +" currentTagRemovals="+otherPilot.tagRemovals+" primaryTags="+primary.tags
    +" completionEvents="+AutopilotLogManager.completions+" passengerCount="+opponent.passengers.size()
    +" replacementDiscards="+(replacement==null?0:replacement.discards));
  if(test.equals("owned-control")) {
   check(!scenes.containsKey(PRIMARY)&&AutonomousFlightManager.forceStops==1&&opponent.discards==1
     &&oldPilot.stops==1&&oldPilot.discards==1,"positive control did not follow current owned teardown");
  } else if(test.equals("unregistered")) {
   check(AutonomousFlightManager.forceStops==0&&opponent.discards==0&&oldPilot.discards==0,
    "unregistered UUID unexpectedly mutated scene participants");
  } else if(test.equals("player")||test.equals("other-mob")) {
   check(scenes.containsKey(PRIMARY)&&AutonomousFlightManager.forceStops==0&&opponent.discards==0
    &&otherPilot.stops==0&&otherPilot.discards==0,"UNSAFE: unknown occupant or aircraft was altered or scene lost");
  } else if(test.equals("additional-player")||test.equals("empty-seat")||test.equals("primary-player")) {
   check(scenes.containsKey(PRIMARY)&&AutonomousFlightManager.forceStops==0&&opponent.discards==0
    &&oldPilot.discards==0&&otherPilot.discards==0,"UNSAFE: unknown occupancy caused teardown or scene loss");
  } else if(test.equals("same-uuid-other-instance")) {
   check(scenes.containsKey(PRIMARY)&&AutonomousFlightManager.forceStops==0&&opponent.discards==0,
    "UNSAFE: UUID-only foreign identity cleared an owned scene");
  } else if(test.equals("partial")) {
   check(scenes.containsKey(PRIMARY)&&primary.tags.contains(RED)&&primary.tags.contains(HOSTILE),
    "UNSAFE: unrecorded partial scene was lost while tags remain");
  } else if(test.equals("complete-player")) {
   check(otherPilot.tags.contains(RED)&&otherPilot.tags.contains(HOSTILE)&&otherPilot.tagRemovals==0,
    "UNSAFE: replacement player tags were altered");
  } else if(test.equals("preexisting-tags")) {
   check(primary.tags.contains(RED)&&primary.tags.contains(HOSTILE)
    &&primaryPilot.tags.contains(RED)&&primaryPilot.tags.contains(HOSTILE),
    "UNSAFE: preexisting primary/pilot tags were removed without ownership proof");
  } else if(test.equals("reloaded-other-instance")) {
   check(replacement.discards==0&&otherPilot.discards==0&&AutopilotLogManager.completions==0,
    "UNSAFE: replacement entity was discarded or completion claimed without verified identity");
  } else throw new IllegalArgumentException(test);
 }
 private static void set(Object obj,String name,Object value)throws Exception{
  Field f=obj.getClass().getDeclaredField(name);f.setAccessible(true);f.set(obj,value);
 }
}
''',
}

CASES = ("owned-control", "unregistered", "player", "other-mob", "additional-player", "empty-seat",
         "primary-player", "same-uuid-other-instance", "partial", "complete-player", "preexisting-tags",
         "reloaded-other-instance")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--java-home", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.absolute()
    output.mkdir(mode=0o700, parents=False, exist_ok=False)
    source = Path(__file__).resolve().parents[1] / "src/main/java/com/wwdebug/autopilot/MutualDogfightValidationManager.java"
    src_dir, classes = output / "stubs", output / "classes"
    empty_classpath, empty_sourcepath = output / "empty-classpath", output / "empty-sourcepath"
    classes.mkdir()
    empty_classpath.mkdir()
    empty_sourcepath.mkdir()
    paths = []
    for name, content in STUBS.items():
        path = src_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        paths.append(path)
    java, javac = args.java_home / "bin/java", args.java_home / "bin/javac"
    repo = source.parents[7]
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    git_blob = subprocess.check_output(["git", "show", revision + ":ww-debug-benchmark/src/main/java/com/wwdebug/autopilot/MutualDogfightValidationManager.java"], cwd=repo)
    tracked_inputs = [source, Path(__file__).resolve(), java.resolve(), javac.resolve(), *paths]
    before = {str(path): sha(path) for path in tracked_inputs}
    version = subprocess.run([str(java), "-version"], capture_output=True, text=True, check=True)
    compile_args = [str(javac), "-proc:none", "--release", "17", "-encoding", "UTF-8", "-implicit:none",
                    "-classpath", str(empty_classpath), "-sourcepath", str(empty_sourcepath),
                    "-d", str(classes), str(source), *map(str, paths)]
    compile_result = subprocess.run(compile_args, cwd=output, capture_output=True, text=True)
    (output / "compile.stdout").write_text(compile_result.stdout, encoding="utf-8")
    (output / "compile.stderr").write_text(compile_result.stderr, encoding="utf-8")
    report = {"revision": revision, "source_sha256": sha(source), "source_git_sha256": hashlib.sha256(git_blob).hexdigest(),
              "test_sha256": sha(Path(__file__)), "java_sha256": sha(java), "javac_sha256": sha(javac),
              "inputs_before": before, "java_version": version.stderr.strip(),
              "scope": "synthetic stand-ins and direct/reflective calls; no world or GameTest; stand-in runtime descriptors differ from Minecraft",
              "compile_command": compile_args, "compile_exit": compile_result.returncode, "cases": {}}
    if compile_result.returncode:
        print(compile_result.stderr, file=sys.stderr)
    else:
        manager_class = classes / "com/wwdebug/autopilot/MutualDogfightValidationManager.class"
        report["compiled_manager_sha256"] = sha(manager_class)
        for case in CASES:
            argv = [str(java), "-Xmx128m", "-Xverify:all", "-cp", str(classes),
                    "com.wwdebug.autopilot.MutualCleanupProbe", case]
            result = subprocess.run(argv, cwd=output, capture_output=True, text=True)
            (output / f"{case}.stdout").write_text(result.stdout, encoding="utf-8")
            (output / f"{case}.stderr").write_text(result.stderr, encoding="utf-8")
            report["cases"][case] = {"exit": result.returncode, "stdout": result.stdout,
                                     "stderr": result.stderr}
            print(f"{case}: exit={result.returncode}; {result.stdout.strip()}")
    after = {str(path): sha(path) for path in tracked_inputs}
    report["inputs_after"] = after
    report["inputs_unchanged"] = before == after
    report["source_matches_git"] = report["source_sha256"] == report["source_git_sha256"]
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 1 if (compile_result.returncode or not report["inputs_unchanged"] or not report["source_matches_git"]
                 or any(v["exit"] for v in report["cases"].values())) else 0


if __name__ == "__main__":
    sys.exit(main())
