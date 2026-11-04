#!/usr/bin/env python3
"""Standalone observation of actual session/formation/arbiter using real manager and stand-in world, terrain, checkpoint and setters.

Never starts Minecraft, touches a world, or asserts physical outcome. Fresh JVM per case.
"""
import argparse, hashlib, json, os, pathlib, shutil, subprocess, sys
ROOT=pathlib.Path(__file__).resolve().parents[1]/'src/main/java'
# Stand-ins are test-only and compiled together with the named production sources.
STUBS = {'net/minecraft/world/level/Level.java': 'package net.minecraft.world.level; import net.minecraft.world.phys.BlockHitResult; public class '
                                         'Level { public boolean isClientSide; public BlockHitResult clip(ClipContext c){return new '
                                         'BlockHitResult();} }',
 'net/minecraft/world/level/ClipContext.java': 'package net.minecraft.world.level; import net.minecraft.world.entity.Entity; import '
                                               'net.minecraft.world.phys.Vec3; public class ClipContext { public enum Block {COLLIDER} '
                                               'public enum Fluid {NONE} public ClipContext(Vec3 a, Vec3 b, Block c, Fluid d, Entity e){} '
                                               '}',
 'net/minecraft/world/phys/HitResult.java': 'package net.minecraft.world.phys; public class HitResult { public enum Type {MISS} public '
                                            'Type getType(){return Type.MISS;} }',
 'net/minecraft/world/phys/BlockHitResult.java': 'package net.minecraft.world.phys; public class BlockHitResult extends HitResult {}',
 'net/minecraft/server/level/ServerLevel.java': 'package net.minecraft.server.level; import java.util.*; import '
                                                'java.util.function.Predicate; import net.minecraft.world.entity.Entity; import '
                                                'net.minecraft.world.level.Level; import net.minecraft.world.phys.AABB; import '
                                                'net.minecraft.server.MinecraftServer; public class ServerLevel extends Level { public '
                                                'List<Entity> entities=new ArrayList<>(); public MinecraftServer getServer(){return null;} '
                                                'public List<Entity> getEntities(Entity e,AABB b,Predicate<? super Entity> p){return '
                                                'entities.stream().filter(x->x!=e).filter(p).toList();} }',
 'net/minecraft/world/entity/Entity.java': 'package net.minecraft.world.entity; import java.util.*; import net.minecraft.world.phys.*; '
                                           'import net.minecraft.world.level.Level; public class Entity { public UUID id; public Level '
                                           'world; public LivingEntity pilot; public Vec3 pos=new Vec3(0,100,0), vel=new Vec3(0,0,0.75); '
                                           'public Set<String> tags=new HashSet<>(); public Entity(UUID u,Level l){id=u;world=l;} public '
                                           'UUID getUUID(){return id;} public net.minecraft.network.chat.Component getName(){return '
                                           'net.minecraft.network.chat.Component.literal("fixture");} public '
                                           'net.minecraft.server.MinecraftServer getServer(){return null;} public void '
                                           'setDeltaMovement(double x,double y,double z){vel=new Vec3(x,y,z);} public Level level(){return '
                                           'world;} public LivingEntity getControllingPassenger(){return pilot;} public boolean '
                                           'isRemoved(){return false;} public boolean onGround(){return false;} public Vec3 '
                                           'position(){return pos;} public Vec3 getDeltaMovement(){return vel;} public Vec3 '
                                           'getLookAngle(){return new Vec3(0,0,1);} public float getYRot(){return 0;} public AABB '
                                           'getBoundingBox(){return new AABB(pos.x,pos.y,pos.z,pos.x+1,pos.y+1,pos.z+1);} public '
                                           'Set<String> getTags(){return tags;} }',
 'net/minecraft/world/entity/LivingEntity.java': 'package net.minecraft.world.entity; import java.util.UUID; import '
                                                 'net.minecraft.world.level.Level; public class LivingEntity extends Entity { public '
                                                 'LivingEntity(){this(new UUID(0,3));} public LivingEntity(UUID id){super(id,null);} }',
 'net/minecraft/world/entity/Mob.java': 'package net.minecraft.world.entity; public class Mob extends LivingEntity { public Mob(){} public '
                                        'Mob(java.util.UUID id){super(id);} }',
 'net/minecraft/world/entity/player/Player.java': 'package net.minecraft.world.entity.player; import '
                                                  'net.minecraft.world.entity.LivingEntity; public class Player extends LivingEntity {}',
 'com/wwdebug/benchmark/BenchmarkManager.java': 'package com.wwdebug.benchmark; import net.minecraft.world.entity.Entity; public class '
                                                'BenchmarkManager {public static void applyControl(Entity e){}}',
 'com/wwdebug/benchmark/ReflectiveAircraft.java': 'package com.wwdebug.benchmark; import java.util.*; import '
                                                  'net.minecraft.world.entity.Entity; public class ReflectiveAircraft {public static '
                                                  'List<String> writes=new ArrayList<>(); public static boolean isAirplane(Entity '
                                                  'e){return true;} public static boolean isControllable(Entity e){return true;} public '
                                                  'static void applyControl(Entity e,float x,float y,float z,float '
                                                  'engine){writes.add(x+","+y+","+z+","+engine);}}',
 'com/wwdebug/autopilot/FlightSnapshot.java': 'package com.wwdebug.autopilot; import net.minecraft.world.entity.Entity; import '
                                              'net.minecraft.world.phys.Vec3; public class FlightSnapshot { private final Entity a; public '
                                              'FlightSnapshot(Entity a){this.a=a;} public static FlightSnapshot capture(Entity a){return '
                                              'new FlightSnapshot(a);} public Vec3 position(){return a.position();} public Vec3 '
                                              'velocity(){return a.getDeltaMovement();} public Vec3 forward(){return a.getLookAngle();} '
                                              'public Vec3 horizontalForward(){return a.getLookAngle();} public double speedBps(){return '
                                              'a.getDeltaMovement().length()*20;} public double horizontalSpeedBps(){return '
                                              'a.getDeltaMovement().horizontalDistance()*20;} public double altitudeAboveGround(){return '
                                              '100;} public boolean onGround(){return false;} public double verticalSpeedBps(){return 0;} '
                                              'public float yawDeg(){return 0;} public float pitchDeg(){return 0;} public double '
                                              'enginePower(){return .8;} public double engineTarget(){return .5;} public double '
                                              'movementYawDeg(){return 0;} public String movementDirection(){return "south";} }',
 'com/wwdebug/autopilot/AutopilotProfileRegistry.java': 'package com.wwdebug.autopilot; import java.util.*; import '
                                                        'net.minecraft.world.entity.Entity; import net.minecraft.server.MinecraftServer; '
                                                        'public class AutopilotProfileRegistry {public static Optional<FlightProfile> '
                                                        'resolve(MinecraftServer s,Entity e){return Optional.of(Probe.profile);} public '
                                                        'static String sourceDescription(){return "fixture";}}',
 'com/wwdebug/autopilot/TerrainAvoidancePlanner.java': 'package com.wwdebug.autopilot; import net.minecraft.world.entity.Entity; import '
                                                       'net.minecraft.world.phys.Vec3; public class TerrainAvoidancePlanner {public static '
                                                       'boolean enabled, marked; public static boolean active(Entity e){return marked;} '
                                                       'static class State {} static Decision plan(Entity e,FlightPhase p,FlightSnapshot '
                                                       'f,FlightControlOutput o,State s){marked=enabled;return new '
                                                       'Decision(enabled,false,"synthetic",new Vec3(1,0,0),160,0,0,0,0,0,false);} record '
                                                       'Decision(boolean active,boolean changed,String mode,Vec3 desiredDirection,double '
                                                       'targetAltitude,double lookAheadBlocks,double directClearanceBlocks,double '
                                                       'selectedClearanceBlocks,double headingOffsetDeg,double climbBlocks,boolean '
                                                       'emergency){String description(){return "synthetic";}}}',
 'com/wwdebug/autopilot/MutualDogfightMissionHoldAdapter.java': 'package com.wwdebug.autopilot; import net.minecraft.world.entity.Entity; '
                                                                'public class MutualDogfightMissionHoldAdapter {public static void '
                                                                'apply(Entity e){}}',
 'com/wwdebug/autopilot/FighterCombatFacade.java': 'package com.wwdebug.autopilot; import net.minecraft.world.entity.Entity; public class '
                                                   'FighterCombatFacade {public static ControlOutcome applyControl(Entity e,boolean '
                                                   'risk){return ControlOutcome.none();}}',
 'com/wwdebug/autopilot/EnergyFighterApexYawAdapter.java': 'package com.wwdebug.autopilot; import java.util.Optional; import '
                                                           'net.minecraft.world.entity.Entity; public class EnergyFighterApexYawAdapter '
                                                           '{public static Optional<ControlProposal> applyControl(Entity e){return '
                                                           'Optional.empty();}}',
 'com/wwdebug/autopilot/DefensiveAirCombatManager.java': 'package com.wwdebug.autopilot; import java.util.Optional; import '
                                                         'net.minecraft.world.entity.Entity; public class DefensiveAirCombatManager '
                                                         '{public static Optional<ControlProposal> applyControl(Entity e){return '
                                                         'Optional.empty();}}',
 'com/wwdebug/autopilot/AirCombatManeuverManager.java': 'package com.wwdebug.autopilot; import java.util.Optional; import '
                                                        'net.minecraft.world.entity.Entity; public class AirCombatManeuverManager {public '
                                                        'static Optional<ControlProposal> applyControl(Entity e){return '
                                                        'Optional.empty();}}',
 'com/wwdebug/autopilot/AutopilotLogManager.java': 'package com.wwdebug.autopilot; import java.util.*; import com.google.gson.JsonObject; '
                                                   'import net.minecraft.server.MinecraftServer; import net.minecraft.world.entity.Entity; '
                                                   'public class AutopilotLogManager {public static List<String> frames=new ArrayList<>(), '
                                                   'adapters=new ArrayList<>(), events=new ArrayList<>(); public static void '
                                                   'writeEvent(MinecraftServer s,Entity e,String t,String r,FlightPhase '
                                                   'p){events.add(t+":"+r);} public static void closeAircraft(MinecraftServer s,Entity '
                                                   'e,FlightPhase p,String r){events.add("close:"+r);} public static void '
                                                   'closeServer(MinecraftServer s){} public static void writeFrame(MinecraftServer '
                                                   's,Entity e,JsonObject f){frames.add(f.toString());} public static void '
                                                   'writeControlAdapter(MinecraftServer s,Entity e,FlightPhase p,String r,FlightSnapshot '
                                                   'f,FlightControlOutput b,FlightControlOutput a){adapters.add(r+":"+a.reason());}}',
 'com/wwdebug/autopilot/Probe.java': 'package com.wwdebug.autopilot;\n'
                                     'import java.util.*; import net.minecraft.server.level.ServerLevel; import '
                                     'net.minecraft.world.entity.*; import net.minecraft.world.entity.player.Player; import '
                                     'net.minecraft.world.phys.Vec3; import net.minecraft.resources.ResourceLocation; import '
                                     'com.wwdebug.benchmark.ReflectiveAircraft;\n'
                                     'public class Probe {static void checkWrite(int n,float x,float y,float z,float engine){String[] '
                                     'v=ReflectiveAircraft.writes.get(n).split(",");float[] want={x,y,z,engine};for(int '
                                     'i=0;i<4;i++)if(!Float.isFinite(Float.parseFloat(v[i]))||!Float.isFinite(want[i])||Math.abs(Float.parseFloat(v[i])-want[i])>0.0001f)throw '
                                     'new AssertionError("setter values at "+n);}\n'
                                     'static FlightProfile profile=new FlightProfile(new '
                                     'ResourceLocation("fixture","a6m"),"fighter","fixture",10.273020653865627,32.723952272022544,22,34.644173364843915,null,null,50);\n'
                                     'public static void main(String[] args) throws Exception {String c=args[0];ServerLevel l=new '
                                     'ServerLevel();Entity a=new Entity(new UUID(0,2),l),leader=new Entity(new UUID(0,1),l);a.vel=new '
                                     'Vec3(0,0,30.779231357359148/20.0);a.pilot=new Mob();leader.pilot=new Mob(new UUID(0,4));boolean '
                                     'collision=c.equals("collision")||c.equals("collision-terrain")||c.equals("collision-timeout");leader.pos=collision?new '
                                     'Vec3(3,100,0):new Vec3(40,100,30);leader.vel=new '
                                     'Vec3(0,0,0.75);leader.tags.add("wwformation:group:g");leader.tags.add("wwformation:leader");a.tags.add("wwformation:slot:1");a.tags.add("wingman-fixture");if(!c.equals("ungrouped"))a.tags.add("wwformation:group:g");l.entities.add(a);l.entities.add(leader);TerrainAvoidancePlanner.enabled=c.equals("terrain")||c.equals("collision-terrain");AutopilotValidationCheckpoint.ticks=(c.equals("timeout")||c.equals("collision-timeout"))?440:439;\n'
                                     'int playerPhaseTicks=-1; FlightPhase playerPhase=null; if(c.equals("player")){var '
                                     'prior=ControlAuthorityArbiter.applyControl(a);System.out.println("setup_authority="+prior+" '
                                     'setup_writes="+ReflectiveAircraft.writes+" '
                                     'setup_session="+AutonomousFlightManager.status(a.getUUID()).isPresent());playerPhaseTicks=AutopilotValidationCheckpoint.session.phaseTicks();playerPhase=AutopilotValidationCheckpoint.session.phase();ReflectiveAircraft.writes.clear();AutopilotLogManager.frames.clear();AutopilotLogManager.adapters.clear();AutopilotLogManager.events.clear();a.pilot=new '
                                     'Player();}\n'
                                     'var auth=ControlAuthorityArbiter.applyControl(a);boolean '
                                     'collisionRisk=AirspaceSafetyProbe.collisionRisk(a);System.out.println("collision_risk="+collisionRisk);if(collisionRisk!=collision)throw '
                                     'new AssertionError("collision probe risk");AutopilotSession '
                                     'session=AutopilotValidationCheckpoint.session;FlightControlOutput '
                                     'out=session==null?null:session.lastOutput();System.out.println("case="+c+" authority="+auth+" '
                                     'checkpoint_calls="+AutopilotValidationCheckpoint.calls+" '
                                     'session_present="+AutonomousFlightManager.status(a.getUUID()).isPresent()+" '
                                     'phase="+(session==null?"null":session.phase())+" '
                                     'phaseTicks="+(session==null?"null":session.phaseTicks())+" '
                                     'safety="+(out==null?"null":out.safetyOverride())+" '
                                     'terrain_marked="+TerrainAvoidancePlanner.marked);System.out.println("writes="+ReflectiveAircraft.writes);System.out.println("frames="+AutopilotLogManager.frames);System.out.println("adapters="+AutopilotLogManager.adapters);System.out.println("events="+AutopilotLogManager.events);\n'
                                     'var expected=switch(c){case "grouped"->ControlAuthorityArbiter.Authority.FORMATION;case '
                                     '"ungrouped"->ControlAuthorityArbiter.Authority.BASE_AUTONOMY;case '
                                     '"terrain"->ControlAuthorityArbiter.Authority.TERRAIN_AVOIDANCE;case '
                                     '"collision","collision-terrain","collision-timeout"->ControlAuthorityArbiter.Authority.COLLISION_AVOIDANCE;case '
                                     '"player"->ControlAuthorityArbiter.Authority.PLAYER_CONTROLLED;case '
                                     '"timeout"->ControlAuthorityArbiter.Authority.BASE_AUTONOMY;default->throw new '
                                     'IllegalArgumentException();};if(auth!=expected)throw new AssertionError("unexpected '
                                     'authority");if(AutopilotValidationCheckpoint.calls!=1)throw new AssertionError("session '
                                     'creation/checkpoint '
                                     'count");if(c.equals("player")){if(!ReflectiveAircraft.writes.isEmpty()||AutonomousFlightManager.status(a.getUUID()).isPresent()||!AutopilotLogManager.frames.isEmpty()||session.phaseTicks()!=playerPhaseTicks||session.phase()!=playerPhase)throw '
                                     'new AssertionError("player '
                                     'cleanup");return;}if(out==null||!out.safetyOverride().equals("turn_speed_recovery"))throw new '
                                     'AssertionError("session recovery not observed");if(AutopilotLogManager.frames.size()!=1)throw new '
                                     'AssertionError("one mission frame required");var '
                                     'frame=com.google.gson.JsonParser.parseString(AutopilotLogManager.frames.get(0)).getAsJsonObject();if(!Float.isFinite(out.x())||!Float.isFinite(out.y())||!Float.isFinite(out.z())||!Float.isFinite(out.engineTarget())||!Float.isFinite(frame.get("control_x").getAsFloat())||!Float.isFinite(frame.get("control_y").getAsFloat())||!Float.isFinite(frame.get("control_z").getAsFloat())||!Float.isFinite(frame.get("engine_target_command").getAsFloat())||!frame.get("safety_override").getAsString().equals(out.safetyOverride())||Math.abs(frame.get("control_x").getAsFloat()-out.x())>0.0001f||Math.abs(frame.get("control_y").getAsFloat()-out.y())>0.0001f||Math.abs(frame.get("control_z").getAsFloat()-out.z())>0.0001f||Math.abs(frame.get("engine_target_command").getAsFloat()-out.engineTarget())>0.0001f)throw '
                                     'new AssertionError("mission frame does not match session planned output");\n'
                                     'if(c.equals("terrain")||c.equals("collision-terrain")){if(ReflectiveAircraft.writes.size()!=1)throw '
                                     'new AssertionError("terrain setter '
                                     'count");checkWrite(0,0.7f,0f,-0.6666667f,1f);}else{checkWrite(0,-out.x(),out.y(),out.z(),out.engineTarget());if(c.equals("collision")){if(ReflectiveAircraft.writes.size()!=2)throw '
                                     'new AssertionError("collision setter '
                                     'count");checkWrite(1,-0.62f,0f,0.1f,0.28f);}if((c.equals("collision-timeout")||c.equals("timeout"))&&ReflectiveAircraft.writes.size()!=1)throw '
                                     'new AssertionError("collision timeout setter '
                                     'count");if(c.equals("grouped"))checkWrite(1,0.62f,0f,0.02f,0.08f);}if(c.equals("terrain")||c.equals("collision-terrain")){if(!AutopilotLogManager.adapters.equals(List.of("synthetic:predictive_terrain_avoidance_synthetic")))throw '
                                     'new AssertionError("terrain adapter reason");}else '
                                     'if(c.equals("collision")){if(AutopilotLogManager.adapters.size()!=1||!AutopilotLogManager.adapters.get(0).endsWith(":predicted_aircraft_collision_avoidance"))throw '
                                     'new AssertionError("collision adapter reason");}else '
                                     'if(c.equals("grouped")){if(AutopilotLogManager.adapters.size()!=1||!AutopilotLogManager.adapters.get(0).endsWith(":formation_slot_tracking"))throw '
                                     'new AssertionError("formation adapter reason");}else '
                                     'if(!AutopilotLogManager.adapters.isEmpty())throw new AssertionError("unexpected adapter");\n'
                                     'if((c.equals("timeout")||c.equals("collision-timeout"))&&session.phase()!=FlightPhase.ABORTED)throw '
                                     'new AssertionError("expected '
                                     'timeout");if(c.equals("grouped")&&(session.phase()!=FlightPhase.TURN_RIGHT||session.phaseTicks()!=440||ReflectiveAircraft.writes.size()!=2))throw '
                                     'new AssertionError("formation setter '
                                     'count");if(c.equals("ungrouped")&&(session.phase()!=FlightPhase.TURN_RIGHT||session.phaseTicks()!=440||ReflectiveAircraft.writes.size()!=1))throw '
                                     'new AssertionError("base setter count");}\n'
                                     '}',
 'com/wwdebug/autopilot/AutopilotValidationCheckpoint.java': 'package com.wwdebug.autopilot; import java.util.UUID; import '
                                                             'net.minecraft.server.MinecraftServer; import '
                                                             'net.minecraft.world.entity.Entity; public class '
                                                             'AutopilotValidationCheckpoint {static AutopilotSession session; static int '
                                                             'ticks=439, calls; static void set(AutopilotSession s,String k,Object '
                                                             'v){try{var '
                                                             'f=AutopilotSession.class.getDeclaredField(k);f.setAccessible(true);f.set(s,v);}catch(ReflectiveOperationException '
                                                             'e){throw new RuntimeException(e);}} public static void '
                                                             'applyIfRequested(MinecraftServer server,Entity entity,AutopilotSession '
                                                             's){calls++;session=s;set(s,"phase",FlightPhase.TURN_RIGHT);set(s,"phaseTicks",ticks);set(s,"missionTicks",1000);set(s,"phaseTargetYaw",170f);} '
                                                             'public static void forget(UUID id){}}',
 'com/wwdebug/autopilot/AutopilotValidationManager.java': 'package com.wwdebug.autopilot; import net.minecraft.server.MinecraftServer; '
                                                          'public class AutopilotValidationManager { public static void '
                                                          'tick(MinecraftServer s){} public static void stopSilently(MinecraftServer s){} '
                                                          '}'}

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--java-home',type=pathlib.Path,required=True)
 parser.add_argument('--dependencies-json',type=pathlib.Path,required=True)
 parser.add_argument('--output',type=pathlib.Path,required=True)
 args=parser.parse_args()
 global JDK, DEPS
 JDK=args.java_home.resolve()/'bin';DEPS=args.dependencies_json.resolve()
 out=args.output.absolute();out.mkdir(mode=0o700);prod=out/'production';fake=out/'fixture';src=out/'stubs';empty=out/'empty';
 for q in (prod,fake,src,empty):q.mkdir()
 paths=[]
 for n,v in STUBS.items():
  f=src/n;f.parent.mkdir(parents=True,exist_ok=True);f.write_text(v);paths.append(f)
 deps=[pathlib.Path(x) for x in json.loads(DEPS.read_text())];
 if not deps or any(not p.is_absolute() or not p.exists() for p in deps):raise ValueError('classpath entries must be existing absolute paths')
 cp=os.pathsep.join(map(str,deps));
 names=['ControlAuthorityArbiter','FormationFlightManager','AirspaceSafetyProbe','MobPilotGate','ControlOutcome','ControlProposal','FlightControlOutput','FlightPhase','AutopilotSession','FlightProfile','AutonomousFlightManager']
 actual=[ROOT/'com/wwdebug/autopilot'/(n+'.java') for n in names]; inputs=actual+paths+[JDK/'java',JDK/'javac',DEPS,pathlib.Path(__file__)];
 def inventory(entries):
  out={}
  for entry in entries:
   files=sorted(f for f in entry.rglob('*') if f.is_file()) if entry.is_dir() else [entry]
   for item in files:out[str(item)]=digest(item)
  return out
 before={str(x):digest(x) for x in inputs}; deps_before=inventory(deps); shutil.copyfile(__file__,out/'runner-snapshot.py'); report={'base':'2585f44fa02b84ed7f593bf9a65798a2b4f056ea','scope':'Actual session/profile/manager/arbiter/formation/geometry; checkpoint, snapshot, terrain decision/active, aircraft setter, world and logger are stand-ins. The session frame records planned rather than final applied controls. No real motion, planner or server is run.','runner_snapshot_sha256':digest(out/'runner-snapshot.py'),'inputs_before':before,'classpath_before':deps_before,'runs':{}}
 def run(name,args):
  r=subprocess.run(args,cwd=out,capture_output=True,text=True,timeout=30);(out/(name+'.stdout')).write_text(r.stdout);(out/(name+'.stderr')).write_text(r.stderr);report['runs'][name]={'argv':args,'exit':r.returncode};print(name,r.returncode,flush=True);return r.returncode
 rc=run('compile-all',[str(JDK/'javac'),'-proc:none','--release','17','-cp',cp,'-sourcepath',str(empty),'-d',str(prod),*map(str,actual),*map(str,paths)])
 if not rc:
  for case in ('grouped','ungrouped','terrain','collision','collision-terrain','collision-timeout','player','timeout'):
   run(case,[str(JDK/'java'),'-Xmx128m','-Xverify:all','-Xlog:class+load=info:file='+str(out/(case+'.classes.log')),'-cp',str(prod)+os.pathsep+cp,'com.wwdebug.autopilot.Probe',case])
 report['inputs_after']={str(x):digest(x) for x in inputs}; report['inputs_unchanged']=report['inputs_before']==report['inputs_after'];report['classpath_after']=inventory(deps);report['classpath_unchanged']=deps_before==report['classpath_after'];report['compiled_production']=inventory([prod]);report['compiled_fixture']=inventory([fake]);(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');return 0 if report['inputs_unchanged'] and report['classpath_unchanged'] and all(x['exit']==0 for x in report['runs'].values()) and len(report['runs'])==9 else 1
if __name__=='__main__':sys.exit(main())
