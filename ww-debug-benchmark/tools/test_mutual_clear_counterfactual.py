#!/usr/bin/env python3
"""Compare synthetic clear variants against the real scene and mission-hold source.

All variants are private source copies compiled against stand-ins in a new output directory;
no production source or Minecraft world is changed.  Results are diagnostic, not a fix.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess


ORIGINAL_CLEAR = '''    static void clear(UUID aircraftUuid) {
        Scene scene = SCENES.remove(aircraftUuid);
        if (scene == null) {
            return;
        }
        Entity opponent = scene.opponent;
        if (opponent != null && !opponent.isRemoved()) {
            cleanupOpponent(opponent);
        }
    }
'''

VARIANTS = {
    "baseline": ORIGINAL_CLEAR,
    "noop": '''    static void clear(UUID aircraftUuid) {
        // Experimental copy only: retain the active scene and do not clean up.
    }
''',
    "mark-completed": '''    static void clear(UUID aircraftUuid) {
        // Experimental copy only: stop scene ticks without removing markers.
        Scene scene = SCENES.get(aircraftUuid);
        if (scene != null) scene.completed = true;
    }
''',
}

PROBE = '''
package com.wwdebug.autopilot;
import java.lang.reflect.*; import java.util.*;
import net.minecraft.server.level.ServerLevel; import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.Mob; import net.minecraft.world.entity.player.Player;
public final class ClearCounterfactualProbe {
 private static final UUID P=new UUID(0,1), O=new UUID(0,2), OP=new UUID(0,3);
 @SuppressWarnings("unchecked") public static void main(String[] args)throws Exception {
  String variant=args[0]; System.setProperty("wwdebug.flightGameTestScenario","dogfight_mutual");
  ServerLevel level=new ServerLevel(); Entity primary=new Entity(level,P), opponent=new Entity(level,O);
  Mob primaryPilot=new Mob(level,new UUID(0,4)); Player replacement=new Player(level,new UUID(0,5));
  primary.setPilot(primaryPilot); opponent.setPilot(replacement);
  primary.addTag("wwcombat:faction:red");primary.addTag("wwcombat:hostile:blue");
  level.addFreshEntity(primary);level.addFreshEntity(opponent);
  AutonomousFlightManager.applyControl(primary);
  Class<?> type=Class.forName("com.wwdebug.autopilot.MutualDogfightValidationManager$Scene");
  Constructor<?> ctor=type.getDeclaredConstructor(ServerLevel.class,Entity.class);ctor.setAccessible(true);
  Object scene=ctor.newInstance(level,primary);set(scene,"started",true);set(scene,"opponent",opponent);
  set(scene,"opponentUuid",O);set(scene,"opponentPilotUuid",OP);set(scene,"primaryPilotUuid",primaryPilot.getUUID());
  set(scene,"ageTicks",1999);set(scene,"primaryInitialShots",48);set(scene,"opponentInitialShots",48);
  Field f=MutualDogfightValidationManager.class.getDeclaredField("SCENES");f.setAccessible(true);
  Map<UUID,Object> scenes=(Map<UUID,Object>)f.get(null);scenes.put(P,scene);
  MutualDogfightValidationManager.clear(P);
  boolean presentAfterClear=scenes.containsKey(P);int playerDiscardsAfterClear=replacement.discards;
  MutualDogfightMissionHoldAdapter.apply(primary);
  String holdReason=AutonomousFlightManager.reason(P);
  if(presentAfterClear)MutualDogfightValidationManager.tick(level,primary,FlightPhase.CRUISE_OUTBOUND);
  System.out.println("variant="+variant+" scene_after_clear="+presentAfterClear
   +" hold_reason="+holdReason+" player_discards_after_clear="+playerDiscardsAfterClear
   +" player_discards_after_tick="+replacement.discards+" opponent_discards="+opponent.discards
   +" force_stops="+AutonomousFlightManager.forceStops+" completion_events="+AutopilotLogManager.completions);
  if(!"mutual_dogfight_mission_hold".equals(holdReason))throw new AssertionError("expected tag-only hold not observed");
  if(variant.equals("baseline") && (presentAfterClear||playerDiscardsAfterClear!=1))throw new AssertionError("baseline control mismatch");
  if(variant.equals("noop") && (!presentAfterClear||playerDiscardsAfterClear!=0||replacement.discards!=1
       ||AutopilotLogManager.completions!=1))throw new AssertionError("noop timeout counterfactual mismatch");
  if(variant.equals("mark-completed") && (!presentAfterClear||replacement.discards!=0
       ||AutopilotLogManager.completions!=0))throw new AssertionError("completion flag counterfactual mismatch");
 }
 private static void set(Object o,String name,Object value)throws Exception{
  Field f=o.getClass().getDeclaredField(name);f.setAccessible(true);f.set(o,value);
 }
}
'''


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--java-home",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    output=args.output.absolute();output.mkdir(mode=0o700,parents=False,exist_ok=False)
    tools=Path(__file__).resolve().parent
    spec=importlib.util.spec_from_file_location("fixture195",tools/"test_mutual_cleanup_standalone.py")
    fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)
    manager=tools.parent/"src/main/java/com/wwdebug/autopilot/MutualDogfightValidationManager.java"
    hold=tools.parent/"src/main/java/com/wwdebug/autopilot/MutualDogfightMissionHoldAdapter.java"
    original=manager.read_text(encoding="utf-8")
    if original.count(ORIGINAL_CLEAR)!=1:raise ValueError("baseline clear no longer matches; no variants executed")
    stubs=dict(fixture.STUBS)
    stubs["net/minecraft/server/level/ServerLevel.java"]=stubs["net/minecraft/server/level/ServerLevel.java"].replace(
        "public final class ServerLevel {", "public final class ServerLevel { public final boolean isClientSide=false;")
    stubs["com/wwdebug/benchmark/ReflectiveAircraft.java"]=stubs["com/wwdebug/benchmark/ReflectiveAircraft.java"].replace(
        "public final class ReflectiveAircraft {", "public final class ReflectiveAircraft { public static boolean isAirplane(Entity e){return true;}")
    stubs["com/wwdebug/autopilot/FlightPhase.java"]=stubs["com/wwdebug/autopilot/FlightPhase.java"].replace(
        "CRUISE_OUTBOUND }", "CRUISE_OUTBOUND; public boolean isTerminal(){return false;} public boolean isLandingPhase(){return false;} }")
    stubs["com/wwdebug/autopilot/MobPilotGate.java"]='''
package com.wwdebug.autopilot; import net.minecraft.world.entity.Entity; import net.minecraft.world.entity.Mob;
final class MobPilotGate { static boolean isMobPiloted(Entity e){return e.getControllingPassenger() instanceof Mob;} }
'''
    stubs["com/wwdebug/autopilot/AutonomousFlightManager.java"]=stubs["com/wwdebug/autopilot/AutonomousFlightManager.java"].replace(
        "public static Optional<SessionStatus> status(UUID id){return Optional.empty();}",
        "public static Optional<SessionStatus> status(UUID id){return SESSIONS.containsKey(id)?Optional.of(new SessionStatus(FlightPhase.CRUISE_OUTBOUND)):Optional.empty();} public static String reason(UUID id){return SESSIONS.get(id).session.transitionReason;}")
    stubs.pop("com/wwdebug/autopilot/MutualCleanupProbe.java")
    stubs["com/wwdebug/autopilot/ClearCounterfactualProbe.java"]=PROBE
    java=args.java_home/"bin/java";javac=args.java_home/"bin/javac"
    repo=tools.parents[1]
    revision=subprocess.check_output(["git","rev-parse","HEAD"],cwd=repo,text=True).strip()
    git_manager=subprocess.check_output(["git","show",revision+":ww-debug-benchmark/src/main/java/com/wwdebug/autopilot/MutualDogfightValidationManager.java"],cwd=repo)
    git_hold=subprocess.check_output(["git","show",revision+":ww-debug-benchmark/src/main/java/com/wwdebug/autopilot/MutualDogfightMissionHoldAdapter.java"],cwd=repo)
    tracked=[manager,hold,tools/"test_mutual_cleanup_standalone.py",Path(__file__).resolve(),java.resolve(),javac.resolve()]
    before={str(path):digest(path) for path in tracked}
    report={"revision":revision,"baseline_manager_sha256":digest(manager),"actual_hold_sha256":digest(hold),
            "manager_matches_git":hashlib.sha256(git_manager).hexdigest()==digest(manager),
            "hold_matches_git":hashlib.sha256(git_hold).hexdigest()==digest(hold),"inputs_before":before,
            "fixture_sha256":digest(tools/"test_mutual_cleanup_standalone.py"),"runner_sha256":digest(Path(__file__)),
            "java_sha256":digest(java),"javac_sha256":digest(javac),
            "scope":"source copies with synthetic stand-ins; no real world, GameTest, or production changes; stub runtime descriptors differ",
            "variants":{}}
    for name,replacement in VARIANTS.items():
        root=output/name;root.mkdir();classes=root/"classes";classes.mkdir()
        empty_cp=root/"empty-classpath";empty_cp.mkdir();empty_sp=root/"empty-sourcepath";empty_sp.mkdir()
        candidate=root/"MutualDogfightValidationManager.java"
        candidate.write_text(original.replace(ORIGINAL_CLEAR,replacement),encoding="utf-8")
        paths=[]
        for filename,content in stubs.items():
            path=root/"stubs"/filename;path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(content,encoding="utf-8");paths.append(path)
        cmd=[str(javac),"-proc:none","--release","17","-encoding","UTF-8","-implicit:none",
             "-classpath",str(empty_cp),"-sourcepath",str(empty_sp),"-d",str(classes),
             str(candidate),str(hold),*map(str,paths)]
        compiled=subprocess.run(cmd,cwd=root,capture_output=True,text=True)
        (root/"compile.stderr").write_text(compiled.stderr,encoding="utf-8")
        result={"candidate_sha256":digest(candidate),"stub_sha256":{str(p.relative_to(root)):digest(p) for p in paths},
                "compile_exit":compiled.returncode,"compile_argv":cmd}
        if compiled.returncode==0:
            result["manager_class_sha256"]=digest(classes/"com/wwdebug/autopilot/MutualDogfightValidationManager.class")
            result["hold_class_sha256"]=digest(classes/"com/wwdebug/autopilot/MutualDogfightMissionHoldAdapter.class")
            run=subprocess.run([str(java),"-Xmx128m","-Xverify:all","-cp",str(classes),
                                "com.wwdebug.autopilot.ClearCounterfactualProbe",name],
                               cwd=root,capture_output=True,text=True)
            (root/"run.stdout").write_text(run.stdout,encoding="utf-8")
            (root/"run.stderr").write_text(run.stderr,encoding="utf-8")
            result.update(exit=run.returncode,stdout=run.stdout,stderr=run.stderr)
            print(name,"exit",run.returncode,run.stdout.strip(),flush=True)
        else:
            print(name,"compile failed",compiled.stderr,flush=True)
        report["variants"][name]=result
    report["inputs_after"]={str(path):digest(path) for path in tracked}
    report["inputs_unchanged"]=report["inputs_before"]==report["inputs_after"]
    (output/"report.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    return 1 if (not report["inputs_unchanged"] or not report["manager_matches_git"] or not report["hold_matches_git"]
                 or any(v.get("compile_exit")!=0 or v.get("exit")!=0 for v in report["variants"].values())) else 0


if __name__=="__main__":
    raise SystemExit(main())
