#!/usr/bin/env python3
"""Standalone contract probe of actual session/formation/arbiter using real manager and stand-in world, terrain, checkpoint and setters.

Never starts Minecraft, touches a world, or asserts physical outcome. Fresh JVM per case.
"""
import argparse, hashlib, json, os, pathlib, shutil, subprocess, sys
ROOT=pathlib.Path(__file__).resolve().parents[1]/'src/main/java'
# Production and explicitly declared stand-ins compile together.
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
                                                  'boolean controllable=true; public static List<String> writes=new ArrayList<>(); public '
                                                  'static boolean isAirplane(Entity e){return true;} public static boolean '
                                                  'isControllable(Entity e){return controllable;} public static void applyControl(Entity '
                                                  'e,float x,float y,float z,float engine){writes.add(x+","+y+","+z+","+engine);}}',
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
                                                                'public class MutualDogfightMissionHoldAdapter {public static boolean '
                                                                'enabled;public static void apply(Entity '
                                                                'e){if(!enabled)return;AutopilotSession '
                                                                's=AutopilotValidationCheckpoint.session;AutopilotValidationCheckpoint.set(s,"phase",FlightPhase.CRUISE_OUTBOUND);AutopilotValidationCheckpoint.set(s,"phaseTicks",0);AutopilotValidationCheckpoint.set(s,"transitionReason","synthetic_hold_change");}}',
 'com/wwdebug/autopilot/FighterCombatFacade.java': 'package com.wwdebug.autopilot; import net.minecraft.world.entity.Entity; import '
                                                   'com.wwdebug.benchmark.ReflectiveAircraft; public class FighterCombatFacade {public '
                                                   'static String mode="none"; public static ControlOutcome applyControl(Entity e,boolean '
                                                   'risk){if(risk)return ControlOutcome.none();if(mode.equals("claimed"))return '
                                                   'ControlOutcome.claimedWithoutProposal(ControlAuthorityArbiter.Authority.OFFENSIVE_COMBAT);if(mode.equals("direct")){ReflectiveAircraft.applyControl(e,0.2f,0f,0.1f,0.7f);return '
                                                   'ControlOutcome.alreadyWrote(ControlAuthorityArbiter.Authority.OFFENSIVE_COMBAT);}return '
                                                   'ControlOutcome.none();}}',
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
                                     'import java.util.*;\n'
                                     'import net.minecraft.server.level.ServerLevel;\n'
                                     'import net.minecraft.world.entity.*;\n'
                                     'import net.minecraft.world.entity.player.Player;\n'
                                     'import net.minecraft.world.phys.Vec3;\n'
                                     'import net.minecraft.resources.ResourceLocation;\n'
                                     'import com.wwdebug.benchmark.ReflectiveAircraft;\n'
                                     'public class Probe {\n'
                                     ' static FlightProfile profile=new FlightProfile(new '
                                     'ResourceLocation("fixture","a6m"),"fighter","fixture",10.273020653865627,32.723952272022544,22,34.644173364843915,null,null,50);\n'
                                     ' static void check(boolean b,String msg){if(!b)throw new AssertionError(msg);}\n'
                                     ' static void checkWrite(int index,float x,float y,float z,float engine){String[] '
                                     'a=ReflectiveAircraft.writes.get(index).split(",");float[] want={x,y,z,engine};for(int '
                                     'i=0;i<4;i++){float '
                                     'v=Float.parseFloat(a[i]);check(Float.isFinite(v)&&Float.isFinite(want[i])&&Math.abs(v-want[i])<0.0001f,"setter '
                                     '"+index+" field "+i);}}\n'
                                     ' static AutopilotSession managerSession(Entity aircraft) throws Exception {var '
                                     'f=AutonomousFlightManager.class.getDeclaredField("SESSIONS");f.setAccessible(true);Object '
                                     'entry=((Map<?,?>)f.get(null)).get(aircraft.getUUID());check(entry!=null,"manager session '
                                     'missing");var '
                                     'af=entry.getClass().getDeclaredField("aircraft");af.setAccessible(true);check(af.get(entry)==aircraft,"manager '
                                     'aircraft identity");var '
                                     'sf=entry.getClass().getDeclaredField("session");sf.setAccessible(true);return '
                                     '(AutopilotSession)sf.get(entry);}\n'
                                     ' static void '
                                     'reset(){ReflectiveAircraft.writes.clear();AutopilotLogManager.frames.clear();AutopilotLogManager.adapters.clear();AutopilotLogManager.events.clear();}\n'
                                     ' public static void main(String[] args) throws Exception {\n'
                                     '  String c=args[0];ServerLevel l=new ServerLevel();Entity a=new Entity(new UUID(0,2),l),leader=new '
                                     'Entity(new UUID(0,1),l);\n'
                                     '  a.vel=new Vec3(0,0,30.779231357359148/20.0);a.pilot=new Mob();leader.pilot=new Mob(new '
                                     'UUID(0,4));\n'
                                     '  boolean risk=c.equals("collision")||c.equals("collision-terrain")||c.equals("collision-timeout");\n'
                                     '  leader.pos=risk?new Vec3(3,100,0):new Vec3(40,100,30);leader.vel=new '
                                     'Vec3(0,0,0.75);leader.tags.add("wwformation:group:g");leader.tags.add("wwformation:leader");a.tags.add("wwformation:slot:1");a.tags.add("wingman-fixture");if(!c.equals("ungrouped"))a.tags.add("wwformation:group:g");l.entities.add(a);l.entities.add(leader);\n'
                                     '  '
                                     'TerrainAvoidancePlanner.enabled=c.equals("terrain")||c.equals("collision-terrain");AutopilotValidationCheckpoint.ticks=c.equals("collision-timeout")?440:(c.equals("recovered")?100:439);\n'
                                     '  FlightPhase priorPhase=null;int priorTicks=-1; AutopilotSession priorSession=null;int '
                                     'priorMissionTicks=-1;\n'
                                     '  if(Set.of("player","empty","client","stale","same-uuid","recovered").contains(c)){\n'
                                     '   var '
                                     'setup=ControlAuthorityArbiter.applyControl(a);check(AutopilotValidationCheckpoint.session!=null,"setup '
                                     'session");if(c.equals("recovered")){priorSession=managerSession(a);check(priorSession==AutopilotValidationCheckpoint.session,"setup '
                                     'manager/checkpoint session identity");check(AutopilotValidationCheckpoint.calls==1,"setup checkpoint '
                                     'count");check(priorSession.lastOutput().safetyOverride().equals("turn_speed_recovery"),"setup '
                                     'recovery '
                                     'missing");priorMissionTicks=priorSession.missionTicks();}priorPhase=AutopilotValidationCheckpoint.session.phase();priorTicks=AutopilotValidationCheckpoint.session.phaseTicks();System.out.println("setup="+setup+" '
                                     'phase="+priorPhase+" ticks="+priorTicks+" writes="+ReflectiveAircraft.writes);reset();\n'
                                     '   if(c.equals("recovered"))a.vel=new Vec3(0,0,40.0/20.0);if(c.equals("same-uuid")){Entity old=a; '
                                     'a=new Entity(old.getUUID(),l);a.pilot=new '
                                     'Mob();a.pos=old.pos;a.vel=old.vel;a.tags.addAll(old.tags);l.entities.remove(old);l.entities.add(a);System.out.println("same_uuid_distinct_object="+(old!=a));} '
                                     'if(c.equals("player"))a.pilot=new '
                                     'Player();if(c.equals("empty"))a.pilot=null;if(c.equals("client"))l.isClientSide=true;if(c.equals("stale"))ReflectiveAircraft.controllable=false;\n'
                                     '  }\n'
                                     '  '
                                     'if(c.equals("combat-claimed"))FighterCombatFacade.mode="claimed";if(c.equals("combat-direct"))FighterCombatFacade.mode="direct";if(c.equals("hold-change"))MutualDogfightMissionHoldAdapter.enabled=true;\n'
                                     '  var authority=ControlAuthorityArbiter.applyControl(a);boolean '
                                     'observedRisk=AirspaceSafetyProbe.collisionRisk(a);AutopilotSession '
                                     'session=AutopilotValidationCheckpoint.session;FlightControlOutput '
                                     'output=session==null?null:session.lastOutput();\n'
                                     '  System.out.println("case="+c+" authority="+authority+" collision_risk="+observedRisk+" '
                                     'terrain_marked="+TerrainAvoidancePlanner.marked+" '
                                     'session_present="+AutonomousFlightManager.status(a.getUUID()).isPresent()+" '
                                     'phase="+(session==null?"null":session.phase())+" '
                                     'ticks="+(session==null?"null":session.phaseTicks())+" '
                                     'safety="+(output==null?"null":output.safetyOverride()));\n'
                                     '  '
                                     'System.out.println("writes="+ReflectiveAircraft.writes);System.out.println("frames="+AutopilotLogManager.frames);System.out.println("adapters="+AutopilotLogManager.adapters);System.out.println("events="+AutopilotLogManager.events);\n'
                                     '  '
                                     'if(c.equals("hold-change")||c.equals("stale")||c.equals("same-uuid")){System.out.println("classification=INCONCLUSIVE_OBSERVATION");return;}\n'
                                     '  check(observedRisk==risk,"risk observation");\n'
                                     '  '
                                     'if(Set.of("player","empty","client").contains(c)){check(authority==(c.equals("player")?ControlAuthorityArbiter.Authority.PLAYER_CONTROLLED:ControlAuthorityArbiter.Authority.NONE),"non-mob/client '
                                     'authority");check(ReflectiveAircraft.writes.isEmpty(),"non-mob/client '
                                     'write");check(AutopilotLogManager.frames.isEmpty(),"non-mob/client session '
                                     'tick");check(session.phase()==priorPhase&&session.phaseTicks()==priorTicks,"non-mob/client phase '
                                     'changed");if(!c.equals("client"))check(AutonomousFlightManager.status(a.getUUID()).isEmpty(),"non-mob '
                                     'stale session");return;}\n'
                                     '  check(output!=null&&AutopilotLogManager.frames.size()==1,"one real session frame");var '
                                     'frame=com.google.gson.JsonParser.parseString(AutopilotLogManager.frames.get(0)).getAsJsonObject();\n'
                                     '  check(frame.get("safety_override").getAsString().equals(output.safetyOverride()),"safety '
                                     'frame");float[] '
                                     'values={output.x(),output.y(),output.z(),output.engineTarget()},logged={frame.get("control_x").getAsFloat(),frame.get("control_y").getAsFloat(),frame.get("control_z").getAsFloat(),frame.get("engine_target_command").getAsFloat()};for(int '
                                     'i=0;i<4;i++)check(Float.isFinite(values[i])&&Float.isFinite(logged[i])&&Math.abs(values[i]-logged[i])<0.0001f,"frame '
                                     'control");\n'
                                     '  if(c.equals("recovered")){check(session==priorSession&&managerSession(a)==priorSession,"session '
                                     'identity changed");check(AutopilotValidationCheckpoint.calls==1,"checkpoint called '
                                     'again");check(session.missionTicks()==priorMissionTicks+1,"mission tick did not '
                                     'continue");check(session.phase()==priorPhase&&session.phaseTicks()==priorTicks+1,"turn phase did not '
                                     'continue");System.out.println("recovered_session_identity=same '
                                     'checkpoint_calls="+AutopilotValidationCheckpoint.calls+" mission_ticks_before="+priorMissionTicks+" '
                                     'mission_ticks_after="+session.missionTicks());check(!output.safetyOverride().equals("turn_speed_recovery"),"recovery '
                                     'still '
                                     'active");check(authority==ControlAuthorityArbiter.Authority.FORMATION&&ReflectiveAircraft.writes.size()==2,"formation '
                                     'should resume");return;}\n'
                                     '  check(output.safetyOverride().equals("turn_speed_recovery"),"turn recovery input missing");\n'
                                     '  '
                                     'if(c.equals("grouped")){check(authority==ControlAuthorityArbiter.Authority.BASE_AUTONOMY,"CONTRACT: '
                                     'grouped recovery must retain base authority");check(ReflectiveAircraft.writes.size()==1,"CONTRACT: '
                                     'grouped recovery must retain base '
                                     'write");checkWrite(0,-output.x(),output.y(),output.z(),output.engineTarget());return;}\n'
                                     '  '
                                     'if(c.equals("ungrouped")){check(authority==ControlAuthorityArbiter.Authority.BASE_AUTONOMY&&ReflectiveAircraft.writes.size()==1,"ungrouped '
                                     'base");checkWrite(0,-output.x(),output.y(),output.z(),output.engineTarget());return;}\n'
                                     '  '
                                     'if(c.equals("collision")){check(authority==ControlAuthorityArbiter.Authority.COLLISION_AVOIDANCE&&ReflectiveAircraft.writes.size()==2,"collision '
                                     'writer");checkWrite(1,-0.62f,0f,0.1f,0.28f);check(AutopilotLogManager.adapters.size()==1&&AutopilotLogManager.adapters.get(0).endsWith(":predicted_aircraft_collision_avoidance"),"collision '
                                     'reason");return;}\n'
                                     '  '
                                     'if(c.equals("terrain")||c.equals("collision-terrain")){check(authority==(risk?ControlAuthorityArbiter.Authority.COLLISION_AVOIDANCE:ControlAuthorityArbiter.Authority.TERRAIN_AVOIDANCE)&&ReflectiveAircraft.writes.size()==1,"terrain '
                                     'injected '
                                     'write");checkWrite(0,0.7f,0f,-0.6666667f,1f);check(AutopilotLogManager.adapters.equals(List.of("synthetic:predictive_terrain_avoidance_synthetic")),"terrain '
                                     'reason");return;}\n'
                                     '  '
                                     'if(c.equals("collision-timeout")){check(session.phase()==FlightPhase.ABORTED&&authority==ControlAuthorityArbiter.Authority.COLLISION_AVOIDANCE&&ReflectiveAircraft.writes.size()==1,"terminal '
                                     'risk-only");checkWrite(0,-output.x(),output.y(),output.z(),output.engineTarget());check(AutopilotLogManager.adapters.isEmpty(),"unexpected '
                                     'collision writer");return;}\n'
                                     '  '
                                     'if(c.equals("combat-claimed")||c.equals("combat-direct")){check(authority==ControlAuthorityArbiter.Authority.OFFENSIVE_COMBAT,"fake '
                                     'combat claim lost");check(ReflectiveAircraft.writes.size()==(c.equals("combat-direct")?2:1),"fake '
                                     'combat setter count");if(c.equals("combat-direct"))checkWrite(1,0.2f,0f,0.1f,0.7f);return;}\n'
                                     '  throw new AssertionError("unknown case "+c);\n'
                                     ' }\n'
                                     '}\n',
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
  for case in ('grouped','ungrouped','recovered','terrain','collision','collision-terrain','collision-timeout','player','empty','client','combat-claimed','combat-direct','stale','same-uuid','hold-change'):
   run(case,[str(JDK/'java'),'-Xmx128m','-Xverify:all','-Xlog:class+load=info:file='+str(out/(case+'.classes.log')),'-cp',str(prod)+os.pathsep+cp,'com.wwdebug.autopilot.Probe',case])
 report['inputs_after']={str(x):digest(x) for x in inputs}; report['inputs_unchanged']=report['inputs_before']==report['inputs_after'];report['classpath_after']=inventory(deps);report['classpath_unchanged']=deps_before==report['classpath_after'];report['compiled_production']=inventory([prod]);report['compiled_fixture']=inventory([fake]);(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');return 0 if report['inputs_unchanged'] and report['classpath_unchanged'] and all(x['exit']==0 for x in report['runs'].values()) and len(report['runs'])==16 else 1
if __name__=='__main__':sys.exit(main())
