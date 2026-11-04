#!/usr/bin/env python3
"""Observe real mutual-scene setup ordering using isolated, instrumented stand-ins.

The manager source is unchanged. All entity creation, registration, mounting and hooks below
are fakes: no Minecraft world, actual Forge callback, GameTest or real ownership is exercised.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess


CASES=("success", "no-opponent-preexisting", "no-pilot-create", "reject-opponent-add",
       "reject-pilot-add", "mount-fails", "equip-fails-preexisting", "equip-exception", "missing-session", "reentrant-clear")


def exact_replace(text, old, new):
    if text.count(old)!=1:
        raise ValueError("unexpected stand-in baseline: " + old)
    return text.replace(old,new)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def observations(case, lines):
    """Check trace structure only; these are not safety or real-world acceptance criteria."""
    def event(label):
        matches=[line for line in lines if line.startswith("TRACE "+label+" ")]
        if len(matches)!=1:
            raise ValueError(f"{case}: expected one {label}, found {len(matches)}")
        return dict(item.split("=",1) for item in matches[0].split()[2:])
    observed={"trace_nonempty":bool(lines)}
    if case=="success":
        added=event("opponent.add.after.true");mounted=event("mount.after")
        before_seed=event("session.create.after");started=event("log_stub.mutual_dogfight_validation_started")
        observed["opponent_unrecorded_after_fake_add"]=added["fake_map_has_opponent"]=="true" and added["opponent_ref_recorded"]=="false"
        observed["pilot_unrecorded_after_fake_mount"]=mounted["fake_pilot_reference"]=="true" and mounted["pilot_uuid_recorded"]=="false"
        observed["session_before_seed_observed"]=before_seed["fake_session"]=="STARTUP:0" and before_seed["opponent_ref_recorded"]=="false"
        observed["session_after_seed_observed_at_started_log"]=started["fake_session"]=="CRUISE_OUTBOUND:9000" and started["started"]=="true"
    elif case in ("reject-opponent-add","reject-pilot-add"):
        label="opponent.add.after.false" if case=="reject-opponent-add" else "pilot.add.after.false"
        rejected=event(label);started=event("log_stub.mutual_dogfight_validation_started")
        field="fake_map_has_opponent" if case=="reject-opponent-add" else "fake_map_has_pilot"
        observed["fake_add_rejected"]=rejected[field]=="false"
        observed["started_with_fake_entity_unregistered_and_fake_mount_success"]=started[field]=="false" and started["fake_pilot_reference"]=="true" and started["started"]=="true"
    elif case=="mount-fails":
        mounted=event("mount.after");failed=event("log_stub.mutual_dogfight_validation_setup_failed")
        observed["fake_mount_failed"]=mounted["fake_pilot_reference"]=="false"
        observed["fake_failure_marked_without_recorded_participants"]=failed["completed"]=="true" and failed["opponent_ref_recorded"]=="false" and failed["pilot_uuid_recorded"]=="false"
    elif case=="equip-fails-preexisting":
        preexisting=event("tag.add.after.primary.wwcombat:faction:red.false")
        failed=event("log_stub.mutual_dogfight_validation_setup_failed")
        observed["fake_existing_tag_was_not_added"]=preexisting["primary_red"]=="true"
        observed["fake_existing_tag_removed_on_failure"]=failed["primary_red"]=="false" and failed["primary_hostile"]=="false"
    elif case=="no-opponent-preexisting":
        preexisting=event("tag.add.after.primary.wwcombat:faction:red.false")
        failed=event("log_stub.mutual_dogfight_validation_setup_failed")
        observed["fake_existing_tag_was_not_added"]=preexisting["primary_red"]=="true"
        observed["fake_existing_tag_removed_on_failure"]=failed["primary_red"]=="false" and failed["primary_hostile"]=="false"
    elif case=="no-pilot-create":
        event("pilot.create.null");failed=event("log_stub.mutual_dogfight_validation_setup_failed")
        observed["fake_opponent_discarded_without_scene_ref"]=failed["opponent_removed"]=="true" and failed["opponent_ref_recorded"]=="false"
    elif case=="equip-exception":
        event("opponent.equip.synthetic_throw");thrown=event("tick.threw.IllegalStateException")
        observed["stub_throw_leaves_unrecorded_scene"]=thrown["scene_present"]=="true" and thrown["started"]=="false" and thrown["opponent_ref_recorded"]=="false" and thrown["pilot_uuid_recorded"]=="false"
    elif case=="missing-session":
        absent=event("session.create.after");thrown=event("tick.threw.IllegalStateException")
        observed["fake_session_not_created"]=absent["fake_session"]=="none"
        observed["actual_seed_threw_with_unrecorded_scene"]=thrown["scene_present"]=="true" and thrown["started"]=="false" and thrown["opponent_ref_recorded"]=="false" and thrown["pilot_uuid_recorded"]=="false"
    elif case=="reentrant-clear":
        after=event("reentry.clear.after");started=event("log_stub.mutual_dogfight_validation_started")
        observed["fake_reentry_removed_scene"]=after["scene_present"]=="false" and after["observer_holds_scene_ref"]=="true"
        observed["orphan_scene_reported_started"]=started["scene_present"]=="false" and started["observer_holds_scene_ref"]=="true" and started["started"]=="true"
    else:
        raise ValueError(f"unknown case {case}")
    return observed


TRACE='''
package com.wwdebug.autopilot;
import java.lang.reflect.*; import java.util.*;
import net.minecraft.server.level.ServerLevel; import net.minecraft.world.entity.Entity;
public final class SetupTrace {
 public static final UUID PRIMARY=new UUID(0,1),PRIMARY_PILOT=new UUID(0,2),OPPONENT=new UUID(0,3),PILOT=new UUID(0,4);
 public static String mode; public static boolean armed,reentered; public static ServerLevel level;
 public static Entity primary,primaryPilot,opponent,opponentPilot; private static Object priorScene;
 @SuppressWarnings("unchecked") public static void mark(String label){
  if(!armed)return;
  try {
   Field f=MutualDogfightValidationManager.class.getDeclaredField("SCENES");f.setAccessible(true);
   Map<UUID,Object> scenes=(Map<UUID,Object>)f.get(null); Object live=scenes.get(PRIMARY);
   if(live!=null)priorScene=live;Object scene=live!=null?live:priorScene;
   String values="scene_present="+(live!=null)+" observer_holds_scene_ref="+(scene!=null);
   if(scene!=null){
    values+=" started="+field(scene,"started")+" completed="+field(scene,"completed")
      +" primary_pilot_recorded="+PRIMARY_PILOT.equals(field(scene,"primaryPilotUuid"))
      +" opponent_ref_recorded="+(opponent!=null&&field(scene,"opponent")==opponent)
      +" opponent_uuid_recorded="+OPPONENT.equals(field(scene,"opponentUuid"))
      +" pilot_uuid_recorded="+PILOT.equals(field(scene,"opponentPilotUuid"));
   }
   values+=" fake_map_has_opponent="+(opponent!=null&&level.getEntity(OPPONENT)==opponent)
    +" fake_map_has_pilot="+(opponentPilot!=null&&level.getEntity(PILOT)==opponentPilot)
    +" fake_pilot_reference="+(opponent!=null&&opponent.getControllingPassenger()==opponentPilot&&opponentPilot!=null)
    +" primary_current_pilot_matches="+(primary.getControllingPassenger()==primaryPilot)
    +" primary_direct_passengers="+primary.passengers.size()
    +" opponent_direct_passengers="+(opponent==null?-1:opponent.passengers.size())
    +" primary_red="+primary.getTags().contains("wwcombat:faction:red")
    +" primary_hostile="+primary.getTags().contains("wwcombat:hostile:blue")
    +" opponent_removed="+(opponent!=null&&opponent.isRemoved())
    +" pilot_removed="+(opponentPilot!=null&&opponentPilot.isRemoved())
    +" fake_session="+AutonomousFlightManager.sessionDescription(OPPONENT);
   System.out.println("TRACE "+label+" "+values);
  }catch(ReflectiveOperationException e){throw new IllegalStateException(e);}
 }
 private static Object field(Object scene,String name)throws ReflectiveOperationException{
  Field f=scene.getClass().getDeclaredField(name);f.setAccessible(true);return f.get(scene);
 }
 public static String role(Entity e){
  return e==primary?"primary":e==primaryPilot?"primaryPilot":e==opponent?"opponent":e==opponentPilot?"opponentPilot":"other";
 }
 static void reenter(){
  if(mode.equals("reentrant-clear")&&!reentered){reentered=true;mark("reentry.clear.before");
   MutualDogfightValidationManager.clear(PRIMARY);mark("reentry.clear.after");}
 }
}
'''

PROBE='''
package com.wwdebug.autopilot;
import net.minecraft.server.level.ServerLevel;import net.minecraft.world.entity.Entity;import net.minecraft.world.entity.Mob;
public final class SetupTraceProbe {
 public static void main(String[] args){
  SetupTrace.mode=args[0];SetupTrace.level=new ServerLevel();
  SetupTrace.primary=new Entity(SetupTrace.level,SetupTrace.PRIMARY);
  SetupTrace.primaryPilot=new Mob(SetupTrace.level,SetupTrace.PRIMARY_PILOT);
  SetupTrace.primary.setPilot(SetupTrace.primaryPilot);
  SetupTrace.level.entities.put(SetupTrace.PRIMARY,SetupTrace.primary);
  SetupTrace.level.entities.put(SetupTrace.PRIMARY_PILOT,SetupTrace.primaryPilot);
  if(args[0].equals("equip-fails-preexisting")||args[0].equals("no-opponent-preexisting")){
   SetupTrace.primary.tags.add("wwcombat:faction:red");SetupTrace.primary.tags.add("wwcombat:hostile:blue");
   SetupTrace.primaryPilot.tags.add("wwcombat:faction:red");SetupTrace.primaryPilot.tags.add("wwcombat:hostile:blue");
  }
  System.setProperty("wwdebug.flightGameTestScenario","dogfight_mutual");SetupTrace.armed=true;
  try {
   MutualDogfightValidationManager.tick(SetupTrace.level,SetupTrace.primary,FlightPhase.CRUISE_OUTBOUND);
   SetupTrace.mark("tick.return");
  } catch(RuntimeException e){
   SetupTrace.mark("tick.threw."+e.getClass().getSimpleName());
  }
 }
}
'''


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--java-home",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args();output=args.output.absolute();output.mkdir(mode=0o700,parents=False,exist_ok=False)
    tools=Path(__file__).resolve().parent;repo=tools.parents[1]
    fixture=tools/"test_mutual_cleanup_standalone.py"
    spec=importlib.util.spec_from_file_location("fixture195",fixture)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    stubs=dict(module.STUBS)
    stubs.pop("com/wwdebug/autopilot/MutualCleanupProbe.java")
    stubs["com/wwdebug/autopilot/SetupTrace.java"]=TRACE
    stubs["com/wwdebug/autopilot/SetupTraceProbe.java"]=PROBE
    stubs["net/minecraft/world/entity/Entity.java"]='''
package net.minecraft.world.entity;
import java.util.*;import com.wwdebug.autopilot.SetupTrace;import net.minecraft.network.chat.Component;
import net.minecraft.server.level.ServerLevel;import net.minecraft.world.phys.Vec3;
public class Entity {
 public final UUID id;public final ServerLevel world;public Entity pilot;public final Set<String> tags=new HashSet<>();
 public final List<Entity> passengers=new ArrayList<>();
 public boolean removed;public Entity(ServerLevel w,UUID id){world=w;this.id=id;}
 public UUID getUUID(){return id;}public ServerLevel level(){return world;}public Entity getControllingPassenger(){return pilot;}
 public void setPilot(Entity p){passengers.clear();pilot=p;if(p!=null)passengers.add(p);}public boolean isRemoved(){return removed;}
 public void discard(){SetupTrace.mark("discard.before");removed=true;SetupTrace.mark("discard.after");}
 public void stopRiding(){SetupTrace.mark("stop_riding");}
 public Set<String> getTags(){return tags;}
 public boolean addTag(String s){SetupTrace.mark("tag.add.before."+SetupTrace.role(this)+"."+s);boolean added=tags.add(s);
  SetupTrace.mark("tag.add.after."+SetupTrace.role(this)+"."+s+"."+added);return added;}
 public boolean removeTag(String s){SetupTrace.mark("tag.remove.before."+SetupTrace.role(this)+"."+s);boolean removed=tags.remove(s);
  SetupTrace.mark("tag.remove.after."+SetupTrace.role(this)+"."+s+"."+removed);return removed;}
 public Component getName(){return Component.literal("AUTOPILOT TEST PRIMARY");}
 public void setCustomName(Component c){}public void setCustomNameVisible(boolean v){}public void setInvulnerable(boolean v){}
 public void moveTo(double x,double y,double z,float yaw,float pitch){}
 public Vec3 getLookAngle(){return new Vec3(0,0,1);}public Vec3 getDeltaMovement(){return new Vec3(0,0,1);}
 public Vec3 position(){return new Vec3(0,0,0);}public double distanceTo(Entity e){return 10;}
 public void setDeltaMovement(Vec3 v){SetupTrace.mark("opponent.velocity");}public float getYRot(){return 0;}
}
'''
    stubs["net/minecraft/world/entity/EntityType.java"]='''
package net.minecraft.world.entity;
import com.wwdebug.autopilot.SetupTrace;import net.minecraft.server.level.ServerLevel;import net.minecraft.world.entity.npc.Villager;
public class EntityType<T extends Entity>{
 private final boolean pilot;public static final EntityType<Villager> VILLAGER=new EntityType<>(true);
 public EntityType(){this(false);}private EntityType(boolean p){pilot=p;}
 @SuppressWarnings("unchecked") public T create(ServerLevel l){
  SetupTrace.mark(pilot?"pilot.create.before":"opponent.create.before");
  if(pilot&&SetupTrace.mode.equals("no-pilot-create")){SetupTrace.mark("pilot.create.null");return null;}
  Entity e=pilot?new Villager(l,SetupTrace.PILOT):new Entity(l,SetupTrace.OPPONENT);
  if(pilot)SetupTrace.opponentPilot=e;else SetupTrace.opponent=e;
  SetupTrace.mark(pilot?"pilot.create.after":"opponent.create.after");return (T)e;
 }
}
'''
    stubs["net/minecraft/world/entity/npc/Villager.java"]='''
package net.minecraft.world.entity.npc;
import java.util.UUID;import com.wwdebug.autopilot.SetupTrace;import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.entity.Entity;import net.minecraft.world.entity.Mob;
public final class Villager extends Mob {
 public Villager(ServerLevel w,UUID id){super(w,id);}public void setNoAi(boolean b){}public void setSilent(boolean b){}
 public boolean startRiding(Entity e,boolean force){
  SetupTrace.mark("mount.before");boolean ok=!SetupTrace.mode.equals("mount-fails");
  if(ok)e.setPilot(this);SetupTrace.mark("mount.after");return ok;
 }
}
'''
    stubs["net/minecraftforge/registries/ForgeRegistries.java"]='''
package net.minecraftforge.registries;
import com.wwdebug.autopilot.SetupTrace;import net.minecraft.resources.ResourceLocation;import net.minecraft.world.entity.EntityType;
public final class ForgeRegistries {
 public static final Registry ENTITY_TYPES=new Registry();
 public static final class Registry { public EntityType<?> getValue(ResourceLocation k){
  SetupTrace.mark("opponent.registry");return SetupTrace.mode.equals("no-opponent-preexisting")?null:new EntityType<>();
 }}
}
'''
    stubs["net/minecraft/server/level/ServerLevel.java"]='''
package net.minecraft.server.level;
import java.util.*;import com.wwdebug.autopilot.SetupTrace;import net.minecraft.server.MinecraftServer;import net.minecraft.world.entity.Entity;
public final class ServerLevel {
 public final Map<UUID,Entity> entities=new HashMap<>();private final MinecraftServer server=new MinecraftServer();
 public MinecraftServer getServer(){return server;}public Entity getEntity(UUID id){return entities.get(id);}
 public boolean addFreshEntity(Entity e){
  boolean opponent=e==SetupTrace.opponent;String label=opponent?"opponent.add":"pilot.add";SetupTrace.mark(label+".before");
  if(opponent)SetupTrace.reenter();
  boolean accepted=!(opponent&&SetupTrace.mode.equals("reject-opponent-add"))
      &&!(!opponent&&SetupTrace.mode.equals("reject-pilot-add"));
  if(accepted)entities.put(e.getUUID(),e);SetupTrace.mark(label+".after."+accepted);return accepted;
 }
}
'''
    stubs["com/wwdebug/autopilot/FlightPhase.java"]='''
package com.wwdebug.autopilot;public enum FlightPhase{STARTUP,CRUISE_OUTBOUND}
'''
    stubs["com/wwdebug/autopilot/AutonomousFlightManager.java"]='''
package com.wwdebug.autopilot;
import java.util.*;import net.minecraft.world.entity.Entity;
public final class AutonomousFlightManager{
 private static final Map<UUID,SessionEntry> SESSIONS=new HashMap<>();
 private static final class SessionEntry{final AutopilotSession session=new AutopilotSession();}
 public static void forceStop(UUID id,String reason){SetupTrace.mark("force_stop");}
 public static void applyControl(Entity e){SetupTrace.mark("session.create.before");
  if(!SetupTrace.mode.equals("missing-session")){
   SessionEntry entry=new SessionEntry();entry.session.phase=FlightPhase.STARTUP;SESSIONS.put(e.getUUID(),entry);
  }
  SetupTrace.mark("session.create.after");}
 public static String sessionDescription(UUID id){SessionEntry e=SESSIONS.get(id);return e==null?"none":e.session.phase+":"+e.session.missionTicks;}
 public static Optional<SessionStatus> status(UUID id){return Optional.empty();}public record SessionStatus(FlightPhase phase){}
}
'''
    stubs["com/wwdebug/benchmark/ReflectiveArmament.java"]='''
package com.wwdebug.benchmark;
import com.wwdebug.autopilot.SetupTrace;import net.minecraft.world.entity.Entity;
public final class ReflectiveArmament {
 public static boolean equipTestMachineGun(Entity e,int n){
  boolean opponent=e==SetupTrace.opponent;SetupTrace.mark(opponent?"opponent.equip.before":"primary.equip.before");
  if(opponent&&SetupTrace.mode.equals("equip-exception")){SetupTrace.mark("opponent.equip.synthetic_throw");throw new IllegalStateException("synthetic equipment failure");}
  boolean ok=!(opponent&&SetupTrace.mode.equals("equip-fails-preexisting"));
  SetupTrace.mark(opponent?"opponent.equip.after":"primary.equip.after");return ok;
 }
 public static int estimatedShotsRemaining(Entity e){return 48;}
}
'''
    stubs["com/wwdebug/autopilot/AutopilotLogManager.java"]='''
package com.wwdebug.autopilot;import net.minecraft.server.MinecraftServer;import net.minecraft.world.entity.Entity;
final class AutopilotLogManager{
 static void writeEvent(MinecraftServer s,Entity e,String event,String reason,FlightPhase p){SetupTrace.mark("log_stub."+event);}
}
'''
    stubs["com/wwdebug/autopilot/SetupTrace.java"]=exact_replace(
        stubs["com/wwdebug/autopilot/SetupTrace.java"]," static void reenter(){"," public static void reenter(){")
    stubs.pop("net/minecraft/world/entity/player/Player.java")
    source=tools.parent/"src/main/java/com/wwdebug/autopilot/MutualDogfightValidationManager.java"
    java=args.java_home/"bin/java";javac=args.java_home/"bin/javac"
    source_dir=output/"stubs";classes=output/"classes";classes.mkdir()
    empty_cp=output/"empty-classpath";empty_cp.mkdir();empty_sp=output/"empty-sourcepath";empty_sp.mkdir()
    paths=[]
    for filename,content in stubs.items():
        path=source_dir/filename;path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(content,encoding="utf-8");paths.append(path)
    revision=subprocess.check_output(["git","rev-parse","HEAD"],cwd=repo,text=True).strip()
    blob=subprocess.check_output(["git","show",revision+":ww-debug-benchmark/src/main/java/com/wwdebug/autopilot/MutualDogfightValidationManager.java"],cwd=repo)
    context_paths=["ww-debug-benchmark/src/main/java/com/wwdebug/autopilot/AutonomousFlightManager.java",
                   "ww-debug-benchmark/src/main/java/com/wwdebug/benchmark/ReflectiveArmament.java"]
    context={}
    for path in context_paths:
        local=repo/path;git_bytes=subprocess.check_output(["git","show",revision+":"+path],cwd=repo)
        context[path]={"sha256":digest(local),"git_sha256":hashlib.sha256(git_bytes).hexdigest(),
                       "source_executed":False}
    tracked=[source,fixture,Path(__file__).resolve(),java.resolve(),javac.resolve(),
             *(repo/path for path in context_paths),*paths]
    before={str(p):digest(p) for p in tracked}
    argv=[str(javac),"-proc:none","--release","17","-encoding","UTF-8","-implicit:none",
          "-classpath",str(empty_cp),"-sourcepath",str(empty_sp),"-d",str(classes),str(source),*map(str,paths)]
    compiled=subprocess.run(argv,cwd=output,capture_output=True,text=True)
    (output/"compile.stderr").write_text(compiled.stderr,encoding="utf-8")
    report={"revision":revision,"source_sha256":digest(source),"source_git_sha256":hashlib.sha256(blob).hexdigest(),
            "runner_sha256":digest(Path(__file__)),"fixture_sha256":digest(fixture),"inputs_before":before,
            "context_sources_not_executed":context,
            "scope":"unchanged manager source plus instrumented stand-ins; no real world, Forge lifecycle or GameTest; stand-in ABI differs",
            "limitations":[
                "success means the expected synthetic trace occurred, not successful real registration, ownership, teardown or runtime safety",
                "reject-add cases explicitly allow fake mounting even though fake registration returned false; actual Minecraft behavior is unverified",
                "reentrant-clear is a synthetic callback during fake addFreshEntity; real callback reachability and ordering are unverified",
                "equip-exception is a direct fake helper throw; the real ReflectiveArmament helper catches ordinary RuntimeException and returns false",
                "fake equipment has no inventory; the real helper can mutate a weapon slot before returning false, and rollback is not observed",
                "missing-session uses a fake applyControl return without creating a session; source inspection shows missing profile can cause a return, but the actual entry point was not run",
                "seed is only observed between session.create.after and started-log boundaries, not through an internal seed hook",
                "trace_nonempty means only that one or more lines were produced; it does not establish complete event coverage",
                "fake map membership and fake pilot references can remain true after fake discard; they do not establish real registration, live passengers or detach",
                "observer_holds_scene_ref is an observer's private reference, not evidence the scene remains in the manager map",
                "log_stub events are calls to a fake logger, not durable telemetry writes",
                "passenger lists, dismount, discard, logging and runtime descriptors are stand-ins and do not prove real Minecraft behavior",
                "JDK executables are hashed; JDK libraries and the complete process environment are not pinned",
            ],
            "compile_argv":argv,"compile_exit":compiled.returncode,"cases":{}}
    if compiled.returncode:
        print(compiled.stderr,flush=True)
    else:
        report["manager_class_sha256"]=digest(classes/"com/wwdebug/autopilot/MutualDogfightValidationManager.class")
        for case in CASES:
            cmd=[str(java),"-Xmx128m","-Xverify:all","-cp",str(classes),
                 "com.wwdebug.autopilot.SetupTraceProbe",case]
            run=subprocess.run(cmd,cwd=output,capture_output=True,text=True)
            (output/(case+".stdout")).write_text(run.stdout,encoding="utf-8")
            (output/(case+".stderr")).write_text(run.stderr,encoding="utf-8")
            try:
                checks=observations(case,run.stdout.splitlines()) if run.returncode==0 else {}
                check_error=""
            except (ValueError,KeyError) as error:
                checks={};check_error=str(error)
            report["cases"][case]={"exit":run.returncode,"trace":run.stdout.splitlines(),"stderr":run.stderr,
                                   "observations":checks,"observation_error":check_error}
            print(case,"exit",run.returncode,"trace-lines",len(run.stdout.splitlines()),flush=True)
    report["inputs_after"]={str(p):digest(p) for p in tracked}
    report["inputs_unchanged"]=before==report["inputs_after"]
    report["source_matches_git"]=report["source_sha256"]==report["source_git_sha256"]
    (output/"report.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    return 1 if (compiled.returncode or not report["inputs_unchanged"] or not report["source_matches_git"]
                 or any(v["sha256"]!=v["git_sha256"] for v in context.values())
                 or len(report["cases"])!=len(CASES)
                 or any(v["exit"] or v["observation_error"] or not all(v["observations"].values())
                        for v in report["cases"].values())) else 0


if __name__=="__main__":raise SystemExit(main())
