#!/usr/bin/env python3
"""Private source-copy candidate observation of actual session/formation/arbiter using real manager and stand-in world, terrain, checkpoint and setters.

Never starts Minecraft, touches a world, or asserts physical outcome. Fresh JVM per case.
"""
import argparse, hashlib, json, os, pathlib, shutil, subprocess, sys
ROOT=pathlib.Path(__file__).resolve().parents[1]/'src/main/java'
# Private source copies and explicit stand-ins only.
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
                                                  'boolean controllable=true; public static boolean reenter=false; public static '
                                                  'List<String> writes=new ArrayList<>(); public static boolean isAirplane(Entity '
                                                  'e){return true;} public static boolean isControllable(Entity e){return controllable;} '
                                                  'public static void applyControl(Entity e,float x,float y,float z,float '
                                                  'engine){if(reenter){reenter=false;com.wwdebug.autopilot.AutonomousFlightManager.applyControl(e);}writes.add(x+","+y+","+z+","+engine);}}',
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
                                                   'ControlOutcome.claimedWithoutProposal(ControlAuthorityArbiter.Authority.OFFENSIVE_COMBAT);if(mode.startsWith("callback-")){AutopilotLogManager.events.add("fake_transition:"+mode+":writes_before="+ReflectiveAircraft.writes.size());if(mode.equals("callback-player"))e.pilot=new '
                                                   'net.minecraft.world.entity.player.Player();if(mode.equals("callback-empty"))e.pilot=null;if(mode.equals("callback-client"))e.level().isClientSide=true;if(mode.equals("callback-terrain")){TerrainAvoidancePlanner.enabled=true;TerrainAvoidancePlanner.marked=true;}}if(mode.equals("change")){AutopilotValidationCheckpoint.set(AutopilotValidationCheckpoint.session,"phase",FlightPhase.CRUISE_OUTBOUND);AutopilotValidationCheckpoint.set(AutopilotValidationCheckpoint.session,"transitionReason","fake_combat_change");}if(mode.equals("pending"))return '
                                                   'ControlOutcome.proposed(ControlProposal.ofRawInputs(ControlAuthorityArbiter.Authority.OFFENSIVE_COMBAT,0.2f,0f,0.1f,0.7f,"fake"));if(mode.equals("direct")){ReflectiveAircraft.applyControl(e,0.2f,0f,0.1f,0.7f);return '
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
                                     'TerrainAvoidancePlanner.enabled=c.equals("terrain")||c.equals("collision-terrain");AutopilotValidationCheckpoint.ticks=c.equals("collision-timeout")?440:((c.equals("recovered")||c.equals("same-uuid")||c.equals("reentry"))?100:439);\n'
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
                                     'if(c.startsWith("callback-"))FighterCombatFacade.mode=c;if(c.equals("combat-claimed"))FighterCombatFacade.mode="claimed";if(c.equals("combat-direct"))FighterCombatFacade.mode="direct";if(c.equals("combat-pending"))FighterCombatFacade.mode="pending";if(c.equals("combat-change"))FighterCombatFacade.mode="change";if(c.equals("reentry"))ReflectiveAircraft.reenter=true;if(c.equals("hold-change"))MutualDogfightMissionHoldAdapter.enabled=true;\n'
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
                                     '  if(c.equals("stale")){check(ReflectiveAircraft.writes.isEmpty(),"early-return fixture must not '
                                     'write");check(session.phase()==priorPhase&&session.phaseTicks()==priorTicks,"early-return fixture '
                                     'ticked stale '
                                     'session");System.out.println("classification=UNKNOWN_FALLBACK_OBSERVED_NOT_SAFETY");return;}\n'
                                     '  '
                                     'if(c.startsWith("callback-")){check(AutopilotLogManager.events.stream().anyMatch(e->e.startsWith("fake_transition:")),"fake '
                                     'callback missing");check(ReflectiveAircraft.writes.size()==1,"CONTRACT: no additional setter after '
                                     'callback change");System.out.println("classification=CALLBACK_GATE_OBSERVED");return;}\n'
                                     '  if(c.equals("other-pending")){var '
                                     'method=ControlAuthorityArbiter.class.getDeclaredMethod("syntheticStationProposal",ControlOutcome.class);method.setAccessible(true);var '
                                     'other=ControlOutcome.proposed(ControlProposal.ofRawInputs(ControlAuthorityArbiter.Authority.OFFENSIVE_COMBAT,.2f,0f,.1f,.7f,"fake"));var '
                                     'station=ControlOutcome.proposed(ControlProposal.ofRawInputs(ControlAuthorityArbiter.Authority.FORMATION,.2f,0f,.1f,.7f,"fake"));check(!((Boolean)method.invoke(null,other)),"non-formation '
                                     'proposal classified as station");check(((Boolean)method.invoke(null,station)),"formation proposal '
                                     'not classified as station");System.out.println("classification=AUTHORITY_PREDICATE_ONLY");return;}\n'
                                     '  if(Set.of("hold-change","same-uuid","combat-change","reentry").contains(c)){int '
                                     'expectedCount=c.equals("reentry")?3:2;check(authority==ControlAuthorityArbiter.Authority.FORMATION,"fixture '
                                     'fallback authority");check(ReflectiveAircraft.writes.size()==expectedCount,"fixture fallback setter '
                                     'count");checkWrite(expectedCount-1,0.62f,0f,0.02f,0.08f);check(!ReflectiveAircraft.writes.get(0).equals(ReflectiveAircraft.writes.get(expectedCount-1)),"invalid '
                                     'token unexpectedly '
                                     'reused");System.out.println("classification=UNKNOWN_FALLBACK_OBSERVED_NOT_SAFETY");return;}\n'
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
                                     '  if(c.equals("grouped")){check(authority==ControlAuthorityArbiter.Authority.FORMATION,"candidate '
                                     'preserves formation authority");check(ReflectiveAircraft.writes.size()==2,"candidate should replace '
                                     'pending '
                                     'write");checkWrite(0,-output.x(),output.y(),output.z(),output.engineTarget());check(ReflectiveAircraft.writes.get(0).equals(ReflectiveAircraft.writes.get(1)),"second '
                                     'must equal first setter arguments");return;}\n'
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
                                     'if(c.equals("combat-claimed")||c.equals("combat-direct")||c.equals("combat-pending")){check(authority==ControlAuthorityArbiter.Authority.OFFENSIVE_COMBAT,"fake '
                                     'combat claim lost");check(ReflectiveAircraft.writes.size()==(c.equals("combat-claimed")?1:2),"fake '
                                     'combat setter count");if(!c.equals("combat-claimed"))checkWrite(1,0.2f,0f,0.1f,0.7f);return;}\n'
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

import difflib

def make_candidate(name, source):
 def once(s,old,new):
  if s.count(old)!=1:raise ValueError(f"{name}: expected one target, found {s.count(old)}")
  return s.replace(old,new)
 if name=='AutonomousFlightManager.java':
  old='''        ReflectiveAircraft.applyControl(aircraft, -applied.x(), applied.y(), applied.z(),
                applied.engineTarget());'''
  replacement='''        captureIntent(aircraft, level, entry, missionPlanned, applied);
        ReflectiveAircraft.applyControl(aircraft, -applied.x(), applied.y(), applied.z(),
                applied.engineTarget());
        completeCapture(aircraft);'''
  source=once(source,old,replacement)
  anchor='''    private record SessionEntry(
'''
  add='''    static final class RecoveryFrame {
        final RecoveryFrame parent; final Entity aircraft; final net.minecraft.world.level.Level level;
        final net.minecraft.world.entity.Mob pilot;
        boolean invalid, complete, closed; int intents;
        SessionEntry entry; FlightControlOutput sessionOutput, planned, adapted; FlightPhase phase;
        int ticks, missionTicks; String transition;
        RecoveryFrame(RecoveryFrame parent, Entity aircraft) {
            this.parent=parent; this.aircraft=aircraft; this.level=aircraft.level();
            this.pilot=MobPilotGate.pilotOf(aircraft).orElse(null);
        }
    }
    private static final ThreadLocal<RecoveryFrame> RECOVERY_CAPTURE = new ThreadLocal<>();
    static RecoveryFrame beginCapture(Entity aircraft) {
        RecoveryFrame prior=RECOVERY_CAPTURE.get(); if (prior!=null) prior.invalid=true;
        RecoveryFrame frame=new RecoveryFrame(prior,aircraft); RECOVERY_CAPTURE.set(frame); return frame;
    }
    static void finishCapture(RecoveryFrame frame) {
        if (RECOVERY_CAPTURE.get()!=frame) frame.invalid=true;
        if (frame.parent==null) RECOVERY_CAPTURE.remove(); else RECOVERY_CAPTURE.set(frame.parent);
        frame.closed=true;
    }
    static boolean hasCaptureForTest() { return RECOVERY_CAPTURE.get()!=null; }
    private static void captureIntent(Entity aircraft, ServerLevel level, SessionEntry entry,
            FlightControlOutput mission, FlightControlOutput applied) {
        RecoveryFrame f=RECOVERY_CAPTURE.get(); if(f==null) return;
        if (++f.intents != 1 || f.aircraft!=aircraft || f.level!=level || f.pilot==null ||
                MobPilotGate.pilotOf(aircraft).orElse(null)!=f.pilot || entry.aircraft!=aircraft) { f.invalid=true; return; }
        f.entry=entry; f.sessionOutput=entry.session.lastOutput(); f.planned=mission; f.adapted=applied;
        f.phase=entry.session.phase(); f.ticks=entry.session.phaseTicks(); f.missionTicks=entry.session.missionTicks();
        f.transition=entry.session.transitionReason();
    }
    private static void completeCapture(Entity aircraft) {
        RecoveryFrame f=RECOVERY_CAPTURE.get(); if(f==null || f.invalid) return;
        f.complete=currentFrame(f,aircraft);
    }
    private static boolean currentFrame(RecoveryFrame f, Entity aircraft) {
        if (f==null || f.invalid || f.intents!=1 || f.aircraft!=aircraft || aircraft.isRemoved() ||
                aircraft.level()!=f.level || aircraft.level().isClientSide || f.pilot==null ||
                MobPilotGate.pilotOf(aircraft).orElse(null)!=f.pilot || f.entry==null ||
                !ReflectiveAircraft.isAirplane(aircraft) || !ReflectiveAircraft.isControllable(aircraft)) return false;
        SessionEntry e=SESSIONS.get(aircraft.getUUID());
        return e==f.entry && e.aircraft==aircraft && e.session.phase()==f.phase &&
                e.session.phaseTicks()==f.ticks && e.session.missionTicks()==f.missionTicks &&
                e.session.lastOutput()==f.sessionOutput && java.util.Objects.equals(e.session.transitionReason(),f.transition);
    }
    static boolean usableCapture(RecoveryFrame f, Entity aircraft) {
        return f!=null && f.closed && f.complete && currentFrame(f,aircraft) &&
                f.phase==FlightPhase.TURN_RIGHT && f.planned!=null &&
                "turn_speed_recovery".equals(f.planned.safetyOverride());
    }

'''
  source=once(source,anchor,add+anchor)
 elif name=='ControlAuthorityArbiter.java':
  old='''        AutonomousFlightManager.applyControl(aircraft);
        MutualDogfightMissionHoldAdapter.apply(aircraft);'''
  replacement='''        AutonomousFlightManager.RecoveryFrame token = AutonomousFlightManager.beginCapture(aircraft);
        try { AutonomousFlightManager.applyControl(aircraft); }
        finally { AutonomousFlightManager.finishCapture(token); }
        MutualDogfightMissionHoldAdapter.apply(aircraft);'''
  source=once(source,old,replacement)
  old='''            if (formation.pendingWrite().isPresent()
                    && !attemptFormationPendingWrite(aircraft, formation.pendingWrite().get(), formationEvaluation)) {
                return rejected(aircraft);
            }'''
  replacement='''            if (formation.pendingWrite().isPresent()) {
                ControlProposal pending = formation.pendingWrite().get();
                if (AutonomousFlightManager.usableCapture(token, aircraft)
                        && formationEvaluation.pilot() == token.pilot && formationEvaluation.level() == token.level) {
                    var applied = token.adapted;
                    pending = ControlProposal.ofRawInputs(formation.authority(), -applied.x(),
                            applied.y(), applied.z(), applied.engineTarget(), "synthetic_recovery_replacement");
                }
                if (!attemptFormationPendingWrite(aircraft, pending, formationEvaluation)) return rejected(aircraft);
            }'''
  source=once(source,old,replacement)
 if POLICY == "unbound" and name == "AutonomousFlightManager.java":
  source=once(source,'MobPilotGate.pilotOf(aircraft).orElse(null)!=f.pilot || f.entry==null ||','f.entry==null ||')
 if POLICY == "unbound" and name == "ControlAuthorityArbiter.java":
  source=once(source,'formationEvaluation.pilot() == token.pilot && formationEvaluation.level() == token.level','formationEvaluation.level() == token.level')
 return source

# All callbacks below are synthetic and cannot establish real runtime reachability.
old=STUBS['com/wwdebug/benchmark/ReflectiveAircraft.java']
old=old.replace('public static boolean controllable=true;', 'public static boolean swapPilotAtBase=false, throwAtBase=false; public static boolean controllable=true;')
old=old.replace('writes.add(x+","+y+","+z+","+engine);', 'writes.add(x+","+y+","+z+","+engine);if(swapPilotAtBase){swapPilotAtBase=false;e.pilot=new net.minecraft.world.entity.Mob(new java.util.UUID(0,99));}if(throwAtBase){throwAtBase=false;throw new RuntimeException("synthetic_setter_exception");}')
STUBS['com/wwdebug/benchmark/ReflectiveAircraft.java']=old
old=STUBS['com/wwdebug/benchmark/BenchmarkManager.java']
old=old.replace('public class BenchmarkManager {public static void applyControl(Entity e){}', 'public class BenchmarkManager {public static boolean enabled; public static void applyControl(Entity e){if(enabled)ReflectiveAircraft.applyControl(e,0.11f,0f,0.12f,0.13f);}')
STUBS['com/wwdebug/benchmark/BenchmarkManager.java']=old
old=STUBS['com/wwdebug/autopilot/AutopilotValidationCheckpoint.java']
old=old.replace('ticks=439, calls;', 'ticks=439, calls; static float targetYaw=170f;').replace('set(s,"phaseTargetYaw",170f);', 'set(s,"phaseTargetYaw",targetYaw);')
STUBS['com/wwdebug/autopilot/AutopilotValidationCheckpoint.java']=old
old=STUBS['com/wwdebug/autopilot/Probe.java']
old=old.replace('AutopilotValidationCheckpoint.ticks=c.equals("collision-timeout")?440:', 'AutopilotValidationCheckpoint.ticks=(c.equals("collision-timeout")||c.equals("timeout"))?440:')
old=old.replace('FlightPhase priorPhase=null;', 'if(c.equals("mob-swap"))ReflectiveAircraft.swapPilotAtBase=true;if(c.equals("throw-base"))ReflectiveAircraft.throwAtBase=true;if(c.equals("prior-writer"))com.wwdebug.benchmark.BenchmarkManager.enabled=true;if(c.equals("phase-transition")){AutopilotValidationCheckpoint.ticks=100;AutopilotValidationCheckpoint.targetYaw=0f;} FlightPhase priorPhase=null;')
old=old.replace('  var authority=ControlAuthorityArbiter.applyControl(a);boolean ', '''  if(c.equals("throw-base")){try{ControlAuthorityArbiter.applyControl(a);throw new AssertionError("no exception");}catch(RuntimeException e){check(e.getMessage().equals("synthetic_setter_exception"),"wrong exception");}try{var f=AutonomousFlightManager.class.getDeclaredMethod("hasCaptureForTest");f.setAccessible(true);check(!((Boolean)f.invoke(null)),"frame leaked");System.out.println("classification=SYNTHETIC_FINALLY_CLEANUP");}catch(NoSuchMethodException e){System.out.println("classification=BASELINE_NO_FRAME");}return;}
  var authority=ControlAuthorityArbiter.applyControl(a);boolean ''')
old=old.replace('if(c.equals("stale")){', '''if(c.equals("mob-swap")){check(a.pilot instanceof Mob && a.pilot.getUUID().equals(new UUID(0,99)),"mob swap not reached");check(authority==ControlAuthorityArbiter.Authority.FORMATION&&ReflectiveAircraft.writes.size()==2,"formation fallback absent");checkWrite(1,0.62f,0f,0.02f,0.08f);System.out.println("classification=SWAPPED_MOB_FALLBACK_NOT_SAFETY");return;}
  if(c.equals("prior-writer")){check(ReflectiveAircraft.writes.size()==3,"prior writer not reached");checkWrite(0,0.11f,0f,0.12f,0.13f);check(ReflectiveAircraft.writes.get(1).equals(ReflectiveAircraft.writes.get(2)),"last did not match same-tick base");System.out.println("classification=PRIOR_WRITER_STANDIN");return;}
  if(c.equals("timeout")){check(session.phase()==FlightPhase.ABORTED&&authority==ControlAuthorityArbiter.Authority.BASE_AUTONOMY&&ReflectiveAircraft.writes.size()==1,"timeout");System.out.println("classification=ABORT_OBSERVED");return;}
  if(c.equals("phase-transition")){check(session.phase()==FlightPhase.STALL_SETUP&&authority==ControlAuthorityArbiter.Authority.FORMATION&&ReflectiveAircraft.writes.size()==2,"phase transition");checkWrite(1,0.62f,0f,0.02f,0.08f);System.out.println("classification=TRANSITION_FALLBACK_NOT_SAFETY");return;}
  if(c.equals("stale")){''')
STUBS['com/wwdebug/autopilot/Probe.java']=old

# One artificial getter exception distinguishes the third call's call site.
entity=STUBS['net/minecraft/world/entity/Entity.java']
entity=entity.replace('public UUID id;', 'public static int getterCalls,throwAt=-1; public static String getterTrace=""; public UUID id;')
entity=entity.replace('public LivingEntity getControllingPassenger(){return pilot;}', 'public LivingEntity getControllingPassenger(){getterCalls++;if(getterCalls==throwAt){getterTrace=java.util.Arrays.toString(Thread.currentThread().getStackTrace());throw new RuntimeException("synthetic_getter_"+getterCalls);}return pilot;}')
STUBS['net/minecraft/world/entity/Entity.java']=entity
probe=STUBS['com/wwdebug/autopilot/Probe.java']
probe=probe.replace('  var authority=ControlAuthorityArbiter.applyControl(a);boolean ', '''  if(c.equals("getter-throw")){Entity.getterCalls=0;Entity.throwAt=3;try{ControlAuthorityArbiter.applyControl(a);throw new AssertionError("no getter exception");}catch(RuntimeException e){check(e.getMessage().equals("synthetic_getter_3"),"wrong getter exception");}boolean frame=false;try{var f=AutonomousFlightManager.class.getDeclaredMethod("hasCaptureForTest");f.setAccessible(true);frame=true;check(!((Boolean)f.invoke(null)),"getter exception leaked frame");}catch(NoSuchMethodException ignored){}check(Entity.getterCalls==3,"getter count");check(ReflectiveAircraft.writes.size()==(frame?0:1),"unexpected prior base write");System.out.println("getter_calls="+Entity.getterCalls+" writes="+ReflectiveAircraft.writes+" frame="+frame+" trace="+Entity.getterTrace);System.out.println("classification=INJECTED_GETTER_EXCEPTION");return;}
  var authority=ControlAuthorityArbiter.applyControl(a);boolean ''')
STUBS['com/wwdebug/autopilot/Probe.java']=probe

def prepare_nested():
 old=STUBS['com/wwdebug/benchmark/ReflectiveAircraft.java']
 old=old.replace('public static boolean swapPilotAtBase=false, throwAtBase=false;', 'public static boolean nestedArbiter=false; public static boolean swapPilotAtBase=false, throwAtBase=false;')
 old=old.replace('if(reenter){reenter=false;', 'if(nestedArbiter){nestedArbiter=false;com.wwdebug.autopilot.ControlAuthorityArbiter.applyControl(e);}if(reenter){reenter=false;')
 STUBS['com/wwdebug/benchmark/ReflectiveAircraft.java']=old
 old=STUBS['com/wwdebug/autopilot/Probe.java']
 old=old.replace('if(c.equals("mob-swap"))ReflectiveAircraft.swapPilotAtBase=true;', 'if(c.equals("nested-arbiter")){ReflectiveAircraft.nestedArbiter=true;AutopilotValidationCheckpoint.ticks=100;}if(c.equals("mob-swap"))ReflectiveAircraft.swapPilotAtBase=true;')
 old=old.replace('if(c.equals("mob-swap")){', 'if(c.equals("nested-arbiter")){check(ReflectiveAircraft.writes.size()==4,"nested writer count");checkWrite(3,0.62f,0f,0.02f,0.08f);try{var f=AutonomousFlightManager.class.getDeclaredMethod("hasCaptureForTest");f.setAccessible(true);check(!((Boolean)f.invoke(null)),"nested frame leak");}catch(NoSuchMethodException ignored){}System.out.println("classification=NESTED_ARBITER_FALLBACK_NOT_SAFETY");return;}if(c.equals("mob-swap")){')
 STUBS['com/wwdebug/autopilot/Probe.java']=old


def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
EXPECTED_SOURCE = {'ControlAuthorityArbiter': '090110ff9896c5020efc0a47056063f1e10dfdf57c706b2273cd29a470bc8a3f', 'FormationFlightManager': 'dcd90dc80255bbfe90fc1e275345c807f899483f4c8ac71f7de83bac85b193e7', 'AirspaceSafetyProbe': '1fd404c89f28bd7f5238c38481a6bbc15f00a0c4d0bde88b8dbaec1bcdc8313d', 'MobPilotGate': '88929c73a9f8719313c6fccd0b40d5c2a7ea4631be1230ef747e206454278fa2', 'ControlOutcome': 'e3bb9f37ca3123dcc8e03d5a6e0f17384258063a03b553f0abe0012a7a287e00', 'ControlProposal': 'adc38454260fff85fc7d4a84a4413fab4aa37e064f7b81ed0f1c902ef03fa4ae', 'FlightControlOutput': '9ccdc3de853f18aafd714fdf9af337510bff828cb1084b84c3cb44b6010263fe', 'FlightPhase': 'ae86d148d0345e3a6ffcb97103d98b9dd4dbc6cb45fe707d2d11ff315d61e29a', 'AutopilotSession': '6febbf679b837f67639a59f62fce9afc7c5a05093962f50ab000a3126d46d4c1', 'FlightProfile': '78a24d92ba80f420596d2de5d3b83288351813314e5cbf5dbf14380bf661d406', 'AutonomousFlightManager': '45a24a85af3d44a1d189a8e0f18fec178f1da4c19639d820b76e75a94488e177'}
FULL_CASES = ('grouped','ungrouped','recovered','terrain','collision','collision-terrain',
              'collision-timeout','timeout','phase-transition','mob-swap','prior-writer','throw-base',
              'player','empty','client','combat-claimed','combat-direct','combat-pending','stale',
              'same-uuid','hold-change','combat-change','reentry','getter-throw','callback-player','callback-empty',
              'callback-client','callback-terrain')
POLICY = None

def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--java-home',type=pathlib.Path,required=True)
 parser.add_argument('--dependencies-json',type=pathlib.Path,required=True)
 parser.add_argument('--output',type=pathlib.Path,required=True)
 parser.add_argument('--mode',choices=('baseline','bound','unbound','nested'),required=True)
 args=parser.parse_args()
 global JDK, DEPS, POLICY
 POLICY=args.mode; JDK=args.java_home.resolve()/'bin'; DEPS=args.dependencies_json.resolve()
 out=args.output.absolute(); out.mkdir(mode=0o700)
 report={'mode':args.mode,'base':'80eab06; source copies only','classification':'INCONCLUSIVE',
         'scope':'test-only stand-ins; no Mixin, real MOD, native setter or world; fallback is not safety',
         'runs':{},'error':None}
 try:
  if args.mode=='nested':prepare_nested()
  prod=out/'production'; fake=out/'fixture'; src=out/'stubs'; empty=out/'empty'
  for q in (prod,fake,src,empty):q.mkdir()
  paths=[]
  for n,v in STUBS.items():
   f=src/n; f.parent.mkdir(parents=True,exist_ok=True); f.write_text(v); paths.append(f)
  deps=[pathlib.Path(x) for x in json.loads(DEPS.read_text())]
  if not deps or any(not p.is_absolute() or not p.exists() for p in deps):raise ValueError('classpath entries must be existing absolute paths')
  cp=os.pathsep.join(map(str,deps)); names=list(EXPECTED_SOURCE)
  originals=[ROOT/'com/wwdebug/autopilot'/(n+'.java') for n in names]
  hashes={p.stem:digest(p) for p in originals}; report['source_hashes']=hashes
  if hashes!=EXPECTED_SOURCE:raise ValueError('fixed #214 source hash mismatch')
  actual=[]
  for original in originals:
   data=original.read_text(); modified=data if args.mode=='baseline' else make_candidate(original.name,data)
   target=out/'source-copy'/original.relative_to(ROOT); target.parent.mkdir(parents=True,exist_ok=True); target.write_text(modified); actual.append(target)
   if modified!=data:(out/(original.stem+'.patch')).write_text(''.join(difflib.unified_diff(data.splitlines(True),modified.splitlines(True),fromfile='original/'+original.name,tofile='candidate/'+original.name)))
  inputs=originals+actual+paths+[JDK/'java',JDK/'javac',DEPS,pathlib.Path(__file__)]
  def inventory(entries):
   found={}
   for entry in entries:
    files=sorted(f for f in entry.rglob('*') if f.is_file()) if entry.is_dir() else [entry]
    for item in files:found[str(item)]=digest(item)
   return found
  before={str(x):digest(x) for x in inputs}; deps_before=inventory(deps)
  report['inputs_before']=before; report['classpath_before']=deps_before
  shutil.copyfile(__file__,out/'runner-snapshot.py'); report['runner_snapshot_sha256']=digest(out/'runner-snapshot.py')
  def run(name,argv):
   report['runs'][name]={'argv':argv,'exit':None}
   try:r=subprocess.run(argv,cwd=out,capture_output=True,text=True,timeout=30)
   except subprocess.TimeoutExpired as e:
    (out/(name+'.stdout')).write_bytes(e.stdout if isinstance(e.stdout,bytes) else (e.stdout or '').encode())
    (out/(name+'.stderr')).write_bytes(e.stderr if isinstance(e.stderr,bytes) else (e.stderr or '').encode())
    raise RuntimeError(name+' timeout') from e
   (out/(name+'.stdout')).write_text(r.stdout); (out/(name+'.stderr')).write_text(r.stderr)
   report['runs'][name]['exit']=r.returncode; print(name,r.returncode,flush=True); return r.returncode
  rc=run('compile-all',[str(JDK/'javac'),'-proc:none','--release','17','-cp',cp,'-sourcepath',str(empty),'-d',str(prod),*map(str,actual),*map(str,paths)])
  if rc:raise RuntimeError('compile failed')
  cases=FULL_CASES if args.mode in ('baseline','bound') else (('mob-swap',) if args.mode=='unbound' else ('nested-arbiter',))
  for case in cases:run(case,[str(JDK/'java'),'-Xmx128m','-Xverify:all','-Xlog:class+load=info:file='+str(out/(case+'.classes.log')),'-cp',str(prod)+os.pathsep+cp,'com.wwdebug.autopilot.Probe',case])
  report['inputs_after']={str(x):digest(x) for x in inputs}; report['inputs_unchanged']=report['inputs_before']==report['inputs_after']
  report['classpath_after']=inventory(deps); report['classpath_unchanged']=deps_before==report['classpath_after']
  report['compiled_production']=inventory([prod]); report['compiled_fixture']=inventory([fake])
  expected={case:0 for case in cases}; expected['compile-all']=0
  if args.mode=='baseline': expected.update(grouped=1,**{'prior-writer':1})
  if args.mode=='unbound': expected['mob-swap']=1
  observed={name:item['exit'] for name,item in report['runs'].items()}
  checks={'case_exits':observed==expected,'inputs_unchanged':report['inputs_unchanged'],'classpath_unchanged':report['classpath_unchanged']}
  if args.mode in ('baseline','bound'):
   getter=(out/'getter-throw.stdout').read_text()
   checks['getter_throw_reached']='classification=INJECTED_GETTER_EXCEPTION' in getter and ('frame=false' if args.mode=='baseline' else 'frame=true') in getter
   checks['getter_throw_callsite']=('FormationFlightManager.evaluateWithPilot' if args.mode=='baseline' else 'AutonomousFlightManager.applyControl') in getter
  if args.mode=='baseline':
   checks['grouped_expected_red']='second must equal first setter arguments' in (out/'grouped.stderr').read_text()
   checks['prior_expected_red']='last did not match same-tick base' in (out/'prior-writer.stderr').read_text()
  if args.mode=='unbound':checks['unbound_expected_red']='AssertionError: setter 1 field 0' in (out/'mob-swap.stderr').read_text()
  if args.mode=='bound':
   checks['mob_swap_reached']='classification=SWAPPED_MOB_FALLBACK_NOT_SAFETY' in (out/'mob-swap.stdout').read_text()
   checks['throw_cleanup_reached']='classification=SYNTHETIC_FINALLY_CLEANUP' in (out/'throw-base.stdout').read_text()
   checks['direct_reentry_observed']='classification=UNKNOWN_FALLBACK_OBSERVED_NOT_SAFETY' in (out/'reentry.stdout').read_text()
  if args.mode=='nested':checks['nested_reached']='classification=NESTED_ARBITER_FALLBACK_NOT_SAFETY' in (out/'nested-arbiter.stdout').read_text()
  target='grouped' if args.mode in ('baseline','bound') else ('mob-swap' if args.mode=='unbound' else 'nested-arbiter')
  loaded=(out/(target+'.classes.log')).read_text().splitlines()
  for name in names:
   found=[line for line in loaded if 'com.wwdebug.autopilot.'+name+' source:' in line]
   checks['class_origin_'+name]=len(found)==1 and str(prod)+'/' in found[0]
  report['checks']=checks
  if all(checks.values()):report['classification']='EXPECTED_OBSERVATIONS_NOT_SAFETY'
 except Exception as e:
  report['error']=type(e).__name__+': '+str(e)
 finally:
  (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
 print(report['classification'],flush=True)
 return 0 if report['classification']=='EXPECTED_OBSERVATIONS_NOT_SAFETY' else 1
if __name__=='__main__':sys.exit(main())
