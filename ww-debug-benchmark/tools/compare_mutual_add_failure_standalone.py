#!/usr/bin/env python3
"""Compare private source copies after synthetic addFreshEntity(false) events.

Only evidence-directory source copies are changed. Creation, registration, equipment, mounting
and callbacks are stand-ins: no world, real Forge callback, GameTest or ownership is exercised.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess


CASES=("success", "reject-opponent-add", "reject-pilot-add", "reject-opponent-add-repeat",
       "reject-pilot-add-repeat", "reentrant-clear")


def exact_replace(text, old, new):
    if text.count(old)!=1:
        raise ValueError("unexpected stand-in baseline: " + old)
    return text.replace(old,new)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def candidate_source(original, variant):
    if variant=="baseline":return original
    variants={
        "guard-return":("return;", "return;"),
        "guard-completed":(
            'scene.completed = true; AutopilotLogManager.writeEvent(level.getServer(), primary, "mutual_dogfight_validation_setup_failed", "opponent_add_false", phase); return;',
            'scene.completed = true; AutopilotLogManager.writeEvent(level.getServer(), primary, "mutual_dogfight_validation_setup_failed", "pilot_add_false", phase); return;'),
        "guard-cleanup":(
            'opponent.discard(); clearFaction(primary, RED_FACTION, HOSTILE_BLUE); scene.completed = true; AutopilotLogManager.writeEvent(level.getServer(), primary, "mutual_dogfight_validation_setup_failed", "opponent_add_false", phase); return;',
            'opponentPilot.discard(); opponent.discard(); clearFaction(primary, RED_FACTION, HOSTILE_BLUE); scene.completed = true; AutopilotLogManager.writeEvent(level.getServer(), primary, "mutual_dogfight_validation_setup_failed", "pilot_add_false", phase); return;'),
    }
    if variant not in variants:raise ValueError("unknown variant")
    opponent_action,pilot_action=variants[variant]
    result=exact_replace(original,"        level.addFreshEntity(opponent);",
                         "        if (!level.addFreshEntity(opponent)) { "+opponent_action+" }")
    return exact_replace(result,"        level.addFreshEntity(opponentPilot);",
                         "        if (!level.addFreshEntity(opponentPilot)) { "+pilot_action+" }")


def observations(variant,case,lines):
    """Compare synthetic traces; exit 0 means observations matched, not a safety pass."""
    def events(prefix):return [line for line in lines if line.startswith("TRACE "+prefix+" ")]
    def last(label):
        matches=events(label)
        if not matches:raise ValueError(f"{variant}/{case}: missing {label}")
        return dict(item.split("=",1) for item in matches[-1].split()[2:])
    final=last("tick.return.2" if case.endswith("-repeat") else "tick.return.1")
    observed={"trace_nonempty":bool(lines),"fake_tick_returned":True}
    if case.endswith("-repeat"):
        observed["hold_called_directly_after_second_fake_tick"]=len(events("hold.after.2"))==1
    if case=="success":
        observed["fake_success_started"]=final["started"]=="true" and final["scene_present"]=="true"
    elif case.startswith("reject-"):
        subject="opponent" if case.startswith("reject-opponent") else "pilot"
        observed["fake_rejection_seen"]=bool(events(subject+".add.after.false"))
        observed["primary_equip_already_called"]=int(final["fake_primary_equips"])>=1
        if variant=="baseline":
            observed["fake_mount_and_started_continued"]=bool(events("mount.after")) and final["started"]=="true"
        else:
            observed["fake_mount_and_session_not_started"]=not events("mount.before") and not events("session.create.before") and final["started"]=="false"
            if variant=="guard-return" and case.endswith("-repeat"):
                observed["retry_repeats_primary_equip"]=int(final["fake_primary_equips"])==2
            if variant in ("guard-completed","guard-cleanup"):
                observed["completed_flag_set"]=final["completed"]=="true"
            if variant=="guard-cleanup":
                observed["preexisting_primary_tags_removed"]=final["primary_red"]=="false" and final["primary_hostile"]=="false"
                expected_reason="sentinel_before_second_hold" if case.endswith("-repeat") else "not_held"
                observed["direct_hold_not_applied_after_fake_tag_removal"]=final["fake_primary_reason"]==expected_reason
                observed["fake_opponent_discard_called"]=final["opponent_removed"]=="true"
                if subject=="pilot":observed["fake_pilot_discard_called"]=final["pilot_removed"]=="true"
            else:
                observed["preexisting_primary_tags_remain"]=final["primary_red"]=="true" and final["primary_hostile"]=="true"
                observed["direct_hold_remains_active"]=final["fake_primary_reason"]=="mutual_dogfight_mission_hold"
                observed["fake_opponent_not_discarded"]=final["opponent_removed"]=="false"
                if subject=="pilot":observed["fake_pilot_not_discarded"]=final["pilot_removed"]=="false"
            if subject=="pilot" and variant!="guard-cleanup":
                observed["fake_opponent_untracked"]=final["fake_map_has_opponent"]=="true" and final["opponent_ref_recorded"]=="false"
    elif case=="reentrant-clear":
        observed["fake_reentry_orphaned_scene"]=final["scene_present"]=="false" and final["started"]=="true"
    else:raise ValueError("unknown case "+case)
    return observed


TRACE='''
package com.wwdebug.autopilot;
import java.lang.reflect.*; import java.util.*;
import net.minecraft.server.level.ServerLevel; import net.minecraft.world.entity.Entity;
public final class SetupTrace {
 public static final UUID PRIMARY=new UUID(0,1),PRIMARY_PILOT=new UUID(0,2),OPPONENT=new UUID(0,3),PILOT=new UUID(0,4);
 public static String mode; public static boolean armed,reentered; public static ServerLevel level;
 public static int opponentCreates,pilotCreates,primaryEquips;
 public static final List<Entity> opponents=new ArrayList<>(),pilots=new ArrayList<>();
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
      +" opponent_uuid_recorded="+(opponent!=null&&opponent.getUUID().equals(field(scene,"opponentUuid")))
      +" pilot_uuid_recorded="+(opponentPilot!=null&&opponentPilot.getUUID().equals(field(scene,"opponentPilotUuid")));
   }
   values+=" fake_map_has_opponent="+(opponent!=null&&level.getEntity(opponent.getUUID())==opponent)
    +" fake_map_has_pilot="+(opponentPilot!=null&&level.getEntity(opponentPilot.getUUID())==opponentPilot)
    +" fake_created_opponents="+opponentCreates+" fake_created_pilots="+pilotCreates
    +" fake_primary_equips="+primaryEquips
    +" fake_registered_opponents="+opponents.stream().filter(e->level.getEntity(e.getUUID())==e).count()
    +" fake_pilot_reference="+(opponent!=null&&opponent.getControllingPassenger()==opponentPilot&&opponentPilot!=null)
    +" primary_current_pilot_matches="+(primary.getControllingPassenger()==primaryPilot)
    +" primary_direct_passengers="+primary.passengers.size()
    +" opponent_direct_passengers="+(opponent==null?-1:opponent.passengers.size())
    +" primary_red="+primary.getTags().contains("wwcombat:faction:red")
    +" primary_hostile="+primary.getTags().contains("wwcombat:hostile:blue")
    +" opponent_removed="+(opponent!=null&&opponent.isRemoved())
    +" pilot_removed="+(opponentPilot!=null&&opponentPilot.isRemoved())
    +" fake_session="+(opponent==null?"none":AutonomousFlightManager.sessionDescription(opponent.getUUID()))
    +" fake_primary_reason="+AutonomousFlightManager.sessionReason(PRIMARY);
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
  AutonomousFlightManager.registerPrimaryForProbe(SetupTrace.primary);
  if(args[0].startsWith("reject-")){
   SetupTrace.primary.tags.add("wwcombat:faction:red");SetupTrace.primary.tags.add("wwcombat:hostile:blue");
   SetupTrace.primaryPilot.tags.add("wwcombat:faction:red");SetupTrace.primaryPilot.tags.add("wwcombat:hostile:blue");
  }
  System.setProperty("wwdebug.flightGameTestScenario","dogfight_mutual");SetupTrace.armed=true;
  try {
   MutualDogfightValidationManager.tick(SetupTrace.level,SetupTrace.primary,FlightPhase.CRUISE_OUTBOUND);
   SetupTrace.mark("hold.before.1");MutualDogfightMissionHoldAdapter.apply(SetupTrace.primary);SetupTrace.mark("hold.after.1");
   SetupTrace.mark("tick.return.1");
   if(args[0].endsWith("-repeat")){
    SetupTrace.mark("second_tick.before");
    MutualDogfightValidationManager.tick(SetupTrace.level,SetupTrace.primary,FlightPhase.CRUISE_OUTBOUND);
    AutonomousFlightManager.setReasonForProbe(SetupTrace.PRIMARY,"sentinel_before_second_hold");
    SetupTrace.mark("hold.before.2");MutualDogfightMissionHoldAdapter.apply(SetupTrace.primary);SetupTrace.mark("hold.after.2");
    SetupTrace.mark("tick.return.2");
   }
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
    parser.add_argument("--variant",choices=("baseline","guard-return","guard-completed","guard-cleanup"),required=True)
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
  int index=pilot?SetupTrace.pilotCreates++:SetupTrace.opponentCreates++;
  java.util.UUID id=new java.util.UUID(0,(pilot?4:3)+100L*index);
  Entity e=pilot?new Villager(l,id):new Entity(l,id);
  if(pilot){SetupTrace.opponentPilot=e;SetupTrace.pilots.add(e);}else{SetupTrace.opponent=e;SetupTrace.opponents.add(e);}
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
public final class ServerLevel {public final boolean isClientSide=false;
 public final Map<UUID,Entity> entities=new HashMap<>();private final MinecraftServer server=new MinecraftServer();
 public MinecraftServer getServer(){return server;}public Entity getEntity(UUID id){return entities.get(id);}
 public boolean addFreshEntity(Entity e){
  boolean opponent=e==SetupTrace.opponent;String label=opponent?"opponent.add":"pilot.add";SetupTrace.mark(label+".before");
  if(opponent)SetupTrace.reenter();
  boolean accepted=!(opponent&&SetupTrace.mode.startsWith("reject-opponent-add"))
      &&!(!opponent&&SetupTrace.mode.startsWith("reject-pilot-add"));
  if(accepted)entities.put(e.getUUID(),e);SetupTrace.mark(label+".after."+accepted);return accepted;
 }
}
'''
    stubs["com/wwdebug/autopilot/FlightPhase.java"]='''
package com.wwdebug.autopilot;public enum FlightPhase{STARTUP,CRUISE_OUTBOUND;
 public boolean isTerminal(){return false;}public boolean isLandingPhase(){return false;}}
'''
    stubs["com/wwdebug/autopilot/AutonomousFlightManager.java"]='''
package com.wwdebug.autopilot;
import java.util.*;import net.minecraft.world.entity.Entity;
public final class AutonomousFlightManager{
 private static final Map<UUID,SessionEntry> SESSIONS=new HashMap<>();
 private static final class SessionEntry{final AutopilotSession session=new AutopilotSession();}
 public static void forceStop(UUID id,String reason){SetupTrace.mark("force_stop");}
 public static void registerPrimaryForProbe(Entity e){SessionEntry entry=new SessionEntry();
  entry.session.phase=FlightPhase.CRUISE_OUTBOUND;entry.session.transitionReason="not_held";SESSIONS.put(e.getUUID(),entry);}
 public static void applyControl(Entity e){SetupTrace.mark("session.create.before");
  if(!SetupTrace.mode.equals("missing-session")){
   SessionEntry entry=new SessionEntry();entry.session.phase=FlightPhase.STARTUP;SESSIONS.put(e.getUUID(),entry);
  }
  SetupTrace.mark("session.create.after");}
 public static String sessionDescription(UUID id){SessionEntry e=SESSIONS.get(id);return e==null?"none":e.session.phase+":"+e.session.missionTicks;}
 public static String sessionReason(UUID id){SessionEntry e=SESSIONS.get(id);return e==null?"none":e.session.transitionReason;}
 public static void setReasonForProbe(UUID id,String reason){SESSIONS.get(id).session.transitionReason=reason;}
 public static Optional<SessionStatus> status(UUID id){SessionEntry e=SESSIONS.get(id);
  return e==null?Optional.empty():Optional.of(new SessionStatus(e.session.phase));}public record SessionStatus(FlightPhase phase){}
}
'''
    stubs["com/wwdebug/autopilot/MobPilotGate.java"]='''
package com.wwdebug.autopilot;import net.minecraft.world.entity.Entity;import net.minecraft.world.entity.Mob;
final class MobPilotGate{static boolean isMobPiloted(Entity e){return e.getControllingPassenger() instanceof Mob;}}
'''
    stubs["com/wwdebug/benchmark/ReflectiveAircraft.java"]=exact_replace(
        stubs["com/wwdebug/benchmark/ReflectiveAircraft.java"],"public final class ReflectiveAircraft {",
        "public final class ReflectiveAircraft { public static boolean isAirplane(Entity e){return true;}")
    stubs["com/wwdebug/benchmark/ReflectiveArmament.java"]='''
package com.wwdebug.benchmark;
import com.wwdebug.autopilot.SetupTrace;import net.minecraft.world.entity.Entity;
public final class ReflectiveArmament {
 public static boolean equipTestMachineGun(Entity e,int n){
  boolean opponent=e==SetupTrace.opponent;SetupTrace.mark(opponent?"opponent.equip.before":"primary.equip.before");
  if(!opponent)SetupTrace.primaryEquips++;
  boolean ok=true;
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
    hold=repo/"ww-debug-benchmark/src/main/java/com/wwdebug/autopilot/MutualDogfightMissionHoldAdapter.java"
    context_paths=["ww-debug-benchmark/src/main/java/com/wwdebug/autopilot/AutonomousFlightManager.java",
                   "ww-debug-benchmark/src/main/java/com/wwdebug/benchmark/ReflectiveArmament.java"]
    context={}
    for path in context_paths:
        local=repo/path;git_bytes=subprocess.check_output(["git","show",revision+":"+path],cwd=repo)
        context[path]={"sha256":digest(local),"git_sha256":hashlib.sha256(git_bytes).hexdigest(),
                       "source_executed":False}
    tracked=[source,hold,fixture,Path(__file__).resolve(),java.resolve(),javac.resolve(),
             *(repo/path for path in context_paths),*paths]
    before={str(p):digest(p) for p in tracked}
    java_version=subprocess.run([str(java),"-version"],capture_output=True,text=True,check=True).stderr.strip()
    candidate_dir=output/"candidate";candidate_dir.mkdir();candidate=candidate_dir/"MutualDogfightValidationManager.java"
    candidate.write_text(candidate_source(source.read_text(encoding="utf-8"),args.variant),encoding="utf-8")
    candidate_before=digest(candidate)
    argv=[str(javac),"-proc:none","--release","17","-encoding","UTF-8","-implicit:none",
          "-classpath",str(empty_cp),"-sourcepath",str(empty_sp),"-d",str(classes),str(candidate),str(hold),*map(str,paths)]
    compiled=subprocess.run(argv,cwd=output,capture_output=True,text=True)
    (output/"compile.stderr").write_text(compiled.stderr,encoding="utf-8")
    hold_blob=subprocess.check_output(["git","show",revision+":ww-debug-benchmark/src/main/java/com/wwdebug/autopilot/MutualDogfightMissionHoldAdapter.java"],cwd=repo)
    report={"revision":revision,"variant":args.variant,"candidate_sha256":candidate_before,"java_version":java_version,
            "hold_sha256":digest(hold),"hold_git_sha256":hashlib.sha256(hold_blob).hexdigest(),
            "source_sha256":digest(source),"source_git_sha256":hashlib.sha256(blob).hexdigest(),
            "runner_sha256":digest(Path(__file__)),"fixture_sha256":digest(fixture),"inputs_before":before,
            "context_sources_not_executed":context,
            "scope":"private manager source copy (modified for candidate variants) plus instrumented stand-ins; no real world, Forge lifecycle or GameTest; stand-in ABI differs",
            "limitations":[
                "success means the expected synthetic trace occurred, not successful real registration, ownership, teardown or runtime safety",
                "reject-add cases explicitly allow fake mounting even though fake registration returned false; actual Minecraft behavior is unverified",
                "fake primary equipment is a call count; it does not model real inventory mutations or rollback",
                "fresh fake entity UUIDs allow controlled retries; real Forge UUID generation, duplicate handling and callback effects differ",
                "candidate source copies are hypotheses only and are not production patches or accepted fixes",
                "directly invoked real hold source acts on a fake primary session and stand-in pilot/aircraft; real scheduling and flight are not exercised",
                "repeat cases deliberately replace only fake session transitionReason with a sentinel before the second direct hold call",
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
                checks=observations(args.variant,case,run.stdout.splitlines()) if run.returncode==0 else {}
                check_error=""
            except (ValueError,KeyError) as error:
                checks={};check_error=str(error)
            report["cases"][case]={"argv":cmd,"exit":run.returncode,"trace":run.stdout.splitlines(),"stderr":run.stderr,
                                   "observations":checks,"observation_error":check_error}
            print(case,"exit",run.returncode,"trace-lines",len(run.stdout.splitlines()),flush=True)
    report["inputs_after"]={str(p):digest(p) for p in tracked}
    report["inputs_unchanged"]=before==report["inputs_after"]
    report["candidate_unchanged"]=candidate_before==digest(candidate)
    report["source_matches_git"]=report["source_sha256"]==report["source_git_sha256"]
    report["hold_matches_git"]=report["hold_sha256"]==report["hold_git_sha256"]
    (output/"report.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    return 1 if (compiled.returncode or not report["inputs_unchanged"] or not report["candidate_unchanged"] or not report["source_matches_git"] or not report["hold_matches_git"]
                 or any(v["sha256"]!=v["git_sha256"] for v in context.values())
                 or len(report["cases"])!=len(CASES)
                 or any(v["exit"] or v["observation_error"] or not all(v["observations"].values())
                        for v in report["cases"].values())) else 0


if __name__=="__main__":raise SystemExit(main())
