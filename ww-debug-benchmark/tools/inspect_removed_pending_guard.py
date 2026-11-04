#!/usr/bin/env python3
"""Observe a private source-copy pending-write guard with synthetic callbacks."""
import argparse,difflib,hashlib,json,os,pathlib,shutil,subprocess,sys
ROOT=pathlib.Path(__file__).resolve().parents[1]/"src/main/java"
STUBS = {'com/wwdebug/autopilot/AirCombatManeuverManager.java': 'package com.wwdebug.autopilot; import java.util.Optional; '
                                                        'import net.minecraft.world.entity.Entity; public class '
                                                        'AirCombatManeuverManager {public static '
                                                        'Optional<ControlProposal> applyControl(Entity e){return '
                                                        'Optional.empty();}}',
 'com/wwdebug/autopilot/AutopilotLogManager.java': 'package com.wwdebug.autopilot; import java.util.*; import '
                                                   'com.google.gson.JsonObject; import '
                                                   'net.minecraft.server.MinecraftServer; import '
                                                   'net.minecraft.world.entity.Entity; public class '
                                                   'AutopilotLogManager {public static List<String> frames=new '
                                                   'ArrayList<>(), adapters=new ArrayList<>(), events=new '
                                                   'ArrayList<>(); public static void writeEvent(MinecraftServer '
                                                   's,Entity e,String t,String r,FlightPhase p){events.add(t+":"+r);} '
                                                   'public static void closeAircraft(MinecraftServer s,Entity '
                                                   'e,FlightPhase p,String r){events.add("close:"+r);} public static '
                                                   'void closeServer(MinecraftServer s){} public static void '
                                                   'writeFrame(MinecraftServer s,Entity e,JsonObject '
                                                   'f){frames.add(f.toString());} public static void '
                                                   'writeControlAdapter(MinecraftServer s,Entity e,FlightPhase '
                                                   'p,String r,FlightSnapshot f,FlightControlOutput '
                                                   'b,FlightControlOutput a){adapters.add(r+":"+a.reason());}}',
 'com/wwdebug/autopilot/AutopilotProfileRegistry.java': 'package com.wwdebug.autopilot; import java.util.*; import '
                                                        'net.minecraft.world.entity.Entity; import '
                                                        'net.minecraft.server.MinecraftServer; public class '
                                                        'AutopilotProfileRegistry {public static '
                                                        'Optional<FlightProfile> resolve(MinecraftServer s,Entity '
                                                        'e){return Optional.of(Probe.profile);} public static String '
                                                        'sourceDescription(){return "fixture";}}',
 'com/wwdebug/autopilot/AutopilotValidationCheckpoint.java': 'package com.wwdebug.autopilot; import java.util.UUID; '
                                                             'import net.minecraft.server.MinecraftServer; import '
                                                             'net.minecraft.world.entity.Entity; public class '
                                                             'AutopilotValidationCheckpoint {static AutopilotSession '
                                                             'session; static int ticks=439, calls; static void '
                                                             'set(AutopilotSession s,String k,Object v){try{var '
                                                             'f=AutopilotSession.class.getDeclaredField(k);f.setAccessible(true);f.set(s,v);}catch(ReflectiveOperationException '
                                                             'e){throw new RuntimeException(e);}} public static void '
                                                             'applyIfRequested(MinecraftServer server,Entity '
                                                             'entity,AutopilotSession '
                                                             's){calls++;session=s;set(s,"phase",FlightPhase.TURN_RIGHT);set(s,"phaseTicks",ticks);set(s,"missionTicks",1000);set(s,"phaseTargetYaw",170f);} '
                                                             'public static void forget(UUID id){}}',
 'com/wwdebug/autopilot/AutopilotValidationManager.java': 'package com.wwdebug.autopilot; import '
                                                          'net.minecraft.server.MinecraftServer; public class '
                                                          'AutopilotValidationManager { public static void '
                                                          'tick(MinecraftServer s){} public static void '
                                                          'stopSilently(MinecraftServer s){} }',
 'com/wwdebug/autopilot/DefensiveAirCombatManager.java': 'package com.wwdebug.autopilot; import java.util.Optional; '
                                                         'import net.minecraft.world.entity.Entity; public class '
                                                         'DefensiveAirCombatManager {public static '
                                                         'Optional<ControlProposal> applyControl(Entity e){return '
                                                         'Optional.empty();}}',
 'com/wwdebug/autopilot/EnergyFighterApexYawAdapter.java': 'package com.wwdebug.autopilot; import java.util.Optional; '
                                                           'import net.minecraft.world.entity.Entity; public class '
                                                           'EnergyFighterApexYawAdapter {public static '
                                                           'Optional<ControlProposal> applyControl(Entity e){return '
                                                           'Optional.empty();}}',
 'com/wwdebug/autopilot/FlightSnapshot.java': 'package com.wwdebug.autopilot; import '
                                              'net.minecraft.world.entity.Entity; import '
                                              'net.minecraft.world.phys.Vec3; public class FlightSnapshot { private '
                                              'final Entity a; public FlightSnapshot(Entity a){this.a=a;} public '
                                              'static FlightSnapshot capture(Entity a){return new FlightSnapshot(a);} '
                                              'public Vec3 position(){return a.position();} public Vec3 '
                                              'velocity(){return a.getDeltaMovement();} public Vec3 forward(){return '
                                              'a.getLookAngle();} public Vec3 horizontalForward(){return '
                                              'a.getLookAngle();} public double speedBps(){return '
                                              'a.getDeltaMovement().length()*20;} public double '
                                              'horizontalSpeedBps(){return '
                                              'a.getDeltaMovement().horizontalDistance()*20;} public double '
                                              'altitudeAboveGround(){return 100;} public boolean onGround(){return '
                                              'false;} public double verticalSpeedBps(){return 0;} public float '
                                              'yawDeg(){return 0;} public float pitchDeg(){return 0;} public double '
                                              'enginePower(){return .8;} public double engineTarget(){return .5;} '
                                              'public double movementYawDeg(){return 0;} public String '
                                              'movementDirection(){return "south";} }',
 'com/wwdebug/autopilot/MutualDogfightMissionHoldAdapter.java': 'package com.wwdebug.autopilot; import '
                                                                'net.minecraft.world.entity.Entity; public class '
                                                                'MutualDogfightMissionHoldAdapter {public static '
                                                                'boolean enabled;public static void apply(Entity '
                                                                'e){if(!enabled)return;AutopilotSession '
                                                                's=AutopilotValidationCheckpoint.session;AutopilotValidationCheckpoint.set(s,"phase",FlightPhase.CRUISE_OUTBOUND);AutopilotValidationCheckpoint.set(s,"phaseTicks",0);AutopilotValidationCheckpoint.set(s,"transitionReason","synthetic_hold_change");}}',
 'com/wwdebug/autopilot/TerrainAvoidancePlanner.java': 'package com.wwdebug.autopilot; import '
                                                       'net.minecraft.world.entity.Entity; import '
                                                       'net.minecraft.world.phys.Vec3; public class '
                                                       'TerrainAvoidancePlanner {public static boolean enabled, '
                                                       'marked; public static boolean active(Entity e){return marked;} '
                                                       'static class State {} static Decision plan(Entity '
                                                       'e,FlightPhase p,FlightSnapshot f,FlightControlOutput o,State '
                                                       's){marked=enabled;return new '
                                                       'Decision(enabled,false,"synthetic",new '
                                                       'Vec3(1,0,0),160,0,0,0,0,0,false);} record Decision(boolean '
                                                       'active,boolean changed,String mode,Vec3 '
                                                       'desiredDirection,double targetAltitude,double '
                                                       'lookAheadBlocks,double directClearanceBlocks,double '
                                                       'selectedClearanceBlocks,double headingOffsetDeg,double '
                                                       'climbBlocks,boolean emergency){String description(){return '
                                                       '"synthetic";}}}',
 'com/wwdebug/benchmark/BenchmarkManager.java': 'package com.wwdebug.benchmark; import '
                                                'net.minecraft.world.entity.Entity; public class BenchmarkManager '
                                                '{public static void applyControl(Entity e){}}',
 'com/wwdebug/benchmark/ReflectiveAircraft.java': 'package com.wwdebug.benchmark; import java.util.*; import '
                                                  'net.minecraft.world.entity.Entity; public class ReflectiveAircraft '
                                                  '{public static boolean controllable=true; public static boolean '
                                                  'reenter=false; public static List<String> writes=new ArrayList<>(); '
                                                  'public static boolean isAirplane(Entity e){return true;} public '
                                                  'static boolean isControllable(Entity e){return controllable;} '
                                                  'public static void applyControl(Entity e,float x,float y,float '
                                                  'z,float '
                                                  'engine){if(reenter){reenter=false;com.wwdebug.autopilot.AutonomousFlightManager.applyControl(e);}writes.add(x+","+y+","+z+","+engine);}}',
 'net/minecraft/server/level/ServerLevel.java': 'package net.minecraft.server.level; import java.util.*; import '
                                                'java.util.function.Predicate; import '
                                                'net.minecraft.world.entity.Entity; import '
                                                'net.minecraft.world.level.Level; import '
                                                'net.minecraft.world.phys.AABB; import '
                                                'net.minecraft.server.MinecraftServer; public class ServerLevel '
                                                'extends Level { public List<Entity> entities=new ArrayList<>(); '
                                                'public MinecraftServer getServer(){return null;} public List<Entity> '
                                                'getEntities(Entity e,AABB b,Predicate<? super Entity> p){return '
                                                'entities.stream().filter(x->x!=e).filter(p).toList();} }',
 'net/minecraft/world/entity/Entity.java': 'package net.minecraft.world.entity; import java.util.*; import '
                                           'net.minecraft.world.phys.*; import net.minecraft.world.level.Level; public '
                                           'class Entity { public UUID id; public Level world; public LivingEntity '
                                           'pilot; public Vec3 pos=new Vec3(0,100,0), vel=new Vec3(0,0,0.75); public '
                                           'Set<String> tags=new HashSet<>(); public Entity(UUID u,Level '
                                           'l){id=u;world=l;} public UUID getUUID(){return id;} public '
                                           'net.minecraft.network.chat.Component getName(){return '
                                           'net.minecraft.network.chat.Component.literal("fixture");} public '
                                           'net.minecraft.server.MinecraftServer getServer(){return null;} public void '
                                           'setDeltaMovement(double x,double y,double z){vel=new Vec3(x,y,z);} public '
                                           'Level level(){return world;} public LivingEntity '
                                           'getControllingPassenger(){return pilot;} public boolean isRemoved(){return '
                                           'false;} public boolean onGround(){return false;} public Vec3 '
                                           'position(){return pos;} public Vec3 getDeltaMovement(){return vel;} public '
                                           'Vec3 getLookAngle(){return new Vec3(0,0,1);} public float getYRot(){return '
                                           '0;} public AABB getBoundingBox(){return new '
                                           'AABB(pos.x,pos.y,pos.z,pos.x+1,pos.y+1,pos.z+1);} public Set<String> '
                                           'getTags(){return tags;} }',
 'net/minecraft/world/entity/LivingEntity.java': 'package net.minecraft.world.entity; import java.util.UUID; import '
                                                 'net.minecraft.world.level.Level; public class LivingEntity extends '
                                                 'Entity { public LivingEntity(){this(new UUID(0,3));} public '
                                                 'LivingEntity(UUID id){super(id,null);} }',
 'net/minecraft/world/entity/Mob.java': 'package net.minecraft.world.entity; public class Mob extends LivingEntity { '
                                        'public Mob(){} public Mob(java.util.UUID id){super(id);} }',
 'net/minecraft/world/entity/player/Player.java': 'package net.minecraft.world.entity.player; import '
                                                  'net.minecraft.world.entity.LivingEntity; public class Player '
                                                  'extends LivingEntity {}',
 'net/minecraft/world/level/ClipContext.java': 'package net.minecraft.world.level; import '
                                               'net.minecraft.world.entity.Entity; import '
                                               'net.minecraft.world.phys.Vec3; public class ClipContext { public enum '
                                               'Block {COLLIDER} public enum Fluid {NONE} public ClipContext(Vec3 a, '
                                               'Vec3 b, Block c, Fluid d, Entity e){} }',
 'net/minecraft/world/level/Level.java': 'package net.minecraft.world.level; import '
                                         'net.minecraft.world.phys.BlockHitResult; public class Level { public boolean '
                                         'isClientSide; public BlockHitResult clip(ClipContext c){return new '
                                         'BlockHitResult();} }',
 'net/minecraft/world/phys/BlockHitResult.java': 'package net.minecraft.world.phys; public class BlockHitResult '
                                                 'extends HitResult {}',
 'net/minecraft/world/phys/HitResult.java': 'package net.minecraft.world.phys; public class HitResult { public enum '
                                            'Type {MISS} public Type getType(){return Type.MISS;} }'}
STUBS['net/minecraft/world/entity/Entity.java']=STUBS['net/minecraft/world/entity/Entity.java'].replace('public boolean isRemoved(){return false;}', 'public boolean removed; public boolean isRemoved(){return removed;}')
STUBS['com/wwdebug/autopilot/FighterCombatFacade.java'] = '''package com.wwdebug.autopilot;
import net.minecraft.world.entity.Entity; import net.minecraft.world.entity.player.Player; import com.wwdebug.benchmark.ReflectiveAircraft;
public class FighterCombatFacade {public static String mode="none"; public static ControlOutcome applyControl(Entity a,boolean risk){
 if(mode.equals("claimed"))return ControlOutcome.claimedWithoutProposal(ControlAuthorityArbiter.Authority.OFFENSIVE_COMBAT);if(mode.equals("direct")){ReflectiveAircraft.applyControl(a,.2f,0f,.1f,.7f);return ControlOutcome.alreadyWrote(ControlAuthorityArbiter.Authority.OFFENSIVE_COMBAT);}
 if(risk)return ControlOutcome.none();
 if(mode.startsWith("formation-")||mode.startsWith("combat-")){AutopilotLogManager.events.add("callback:"+mode+":writes_before="+ReflectiveAircraft.writes.size());if(mode.endsWith("-player"))a.pilot=new Player();if(mode.endsWith("-empty"))a.pilot=null;if(mode.endsWith("-removed")){a.removed=true;a.pilot=null;}if(mode.endsWith("-removed-only")||mode.endsWith("-removed-player"))a.removed=true;if(mode.endsWith("-client-player"))a.level().isClientSide=true;if(mode.endsWith("-client"))a.level().isClientSide=true;if(mode.endsWith("-terrain")){TerrainAvoidancePlanner.enabled=true;TerrainAvoidancePlanner.marked=true;}if(mode.startsWith("combat-"))return ControlOutcome.proposed(ControlProposal.ofRawInputs(ControlAuthorityArbiter.Authority.OFFENSIVE_COMBAT,.2f,0f,.1f,.7f,"fixture-pending"));}return ControlOutcome.none();}}'''
STUBS['com/wwdebug/autopilot/Probe.java'] = '''package com.wwdebug.autopilot;
import java.util.*; import net.minecraft.server.level.ServerLevel; import net.minecraft.world.entity.*; import net.minecraft.world.phys.Vec3; import net.minecraft.resources.ResourceLocation; import com.wwdebug.benchmark.ReflectiveAircraft;
public class Probe {static FlightProfile profile=new FlightProfile(new ResourceLocation("fixture","a6m"),"fighter","fixture",10.273020653865627,32.723952272022544,22,34.644173364843915,null,null,50);
static void check(boolean b,String m){if(!b)throw new AssertionError(m);}static void checkWrite(int n,float x,float y,float z,float engine){String[] s=ReflectiveAircraft.writes.get(n).split(",");float[] w={x,y,z,engine};for(int i=0;i<4;i++){float v=Float.parseFloat(s[i]);check(Float.isFinite(v)&&Math.abs(v-w[i])<.0001f,"setter "+n+" field "+i);}}
public static void main(String[] args)throws Exception{String c=args[0];ServerLevel l=new ServerLevel();Entity a=new Entity(new UUID(0,2),l),leader=new Entity(new UUID(0,1),l);a.vel=new Vec3(0,0,30.779231357359148/20.);a.pilot=new Mob();leader.pilot=new Mob(new UUID(0,4));boolean risk=c.equals("risk")||c.equals("risk-only");leader.pos=risk?new Vec3(3,100,0):new Vec3(40,100,30);leader.vel=new Vec3(0,0,.75);leader.tags.add("wwformation:group:g");leader.tags.add("wwformation:leader");a.tags.add("wwformation:slot:1");a.tags.add("wwformation:group:g");l.entities.add(a);l.entities.add(leader);AutopilotValidationCheckpoint.ticks=c.equals("risk-only")?440:439;if(c.startsWith("formation-")||c.startsWith("combat-"))FighterCombatFacade.mode=c;if(c.equals("direct"))FighterCombatFacade.mode="direct";if(c.equals("claimed"))FighterCombatFacade.mode="claimed";
var markerField=ControlAuthorityArbiter.class.getDeclaredField("LAST_AUTHORITY");markerField.setAccessible(true); @SuppressWarnings("unchecked") Map<UUID,ControlAuthorityArbiter.Authority> markers=(Map<UUID,ControlAuthorityArbiter.Authority>)markerField.get(null); UUID aliasUuid=new UUID(a.getUUID().getMostSignificantBits(),a.getUUID().getLeastSignificantBits());Entity alias=new Entity(aliasUuid,l); check(alias!=a,"alias entity identity");check(alias.getUUID()!=a.getUUID()&&alias.getUUID().equals(a.getUUID()),"UUID equal value distinct reference"); markers.put(alias.getUUID(),c.equals("claimed")?ControlAuthorityArbiter.Authority.FORMATION:ControlAuthorityArbiter.Authority.OFFENSIVE_COMBAT);UUID otherId=new UUID(0,777);markers.put(otherId,ControlAuthorityArbiter.Authority.OFFENSIVE_COMBAT);System.out.println("marker_seeded_on_distinct_same_uuid_object="+(alias!=a)+" uuid_equal_distinct_reference="+(alias.getUUID()!=a.getUUID()&&alias.getUUID().equals(a.getUUID()))); var result=ControlAuthorityArbiter.applyControl(a);boolean observedRisk=AirspaceSafetyProbe.collisionRisk(a);var f=ControlAuthorityArbiter.class.getDeclaredField("LAST_AUTHORITY");f.setAccessible(true);Object marker=((Map<?,?>)f.get(null)).get(a.getUUID());System.out.println("case="+c+" authority="+result+" marker="+marker+" risk="+observedRisk+" pilot="+(a.pilot==null?"empty":a.pilot.getClass().getSimpleName())+" client="+a.level().isClientSide+" terrain="+TerrainAvoidancePlanner.marked);System.out.println("writes="+ReflectiveAircraft.writes);System.out.println("events="+AutopilotLogManager.events);System.out.println("adapters="+AutopilotLogManager.adapters);System.out.println("other_uuid_marker="+markers.get(otherId));check(markers.get(otherId)==ControlAuthorityArbiter.Authority.OFFENSIVE_COMBAT,"other UUID marker changed");
check(!ReflectiveAircraft.writes.isEmpty(),"base call missing");checkWrite(0,-.35099998f,0f,-.15f,1f);if(c.equals("risk")){check(observedRisk&&result==ControlAuthorityArbiter.Authority.COLLISION_AVOIDANCE&&ReflectiveAircraft.writes.size()==2,"collision direct control");checkWrite(1,-.62f,0f,.1f,.28f);return;}if(c.equals("risk-only")){check(observedRisk&&result==ControlAuthorityArbiter.Authority.COLLISION_AVOIDANCE&&ReflectiveAircraft.writes.size()==1,"terminal risk only");return;}if(c.equals("claimed")){check(result==ControlAuthorityArbiter.Authority.OFFENSIVE_COMBAT&&ReflectiveAircraft.writes.size()==1,"claimed without proposal");check(marker==ControlAuthorityArbiter.Authority.OFFENSIVE_COMBAT,"claimed marker not updated from FORMATION seed");System.out.println("claimed_marker_seed=FORMATION claimed_marker_after="+marker);return;}if(c.equals("direct")){check(result==ControlAuthorityArbiter.Authority.OFFENSIVE_COMBAT&&ReflectiveAircraft.writes.size()==2,"direct writer");checkWrite(1,.2f,0f,.1f,.7f);return;}check(!observedRisk,"unexpected collision risk");check(AutopilotLogManager.events.stream().anyMatch(e->e.startsWith("callback:"+c+":writes_before=1")),"callback must follow base");if(c.endsWith("-terrain")){check(result==ControlAuthorityArbiter.Authority.TERRAIN_AVOIDANCE&&ReflectiveAircraft.writes.size()==1,"terrain gate");return;}if(c.endsWith("-removed-only")){check(a.removed&&a.pilot instanceof Mob,"removed mob setup");check(ReflectiveAircraft.writes.size()==1,"CONTRACT: no pending setter after removed callback");check(result==ControlAuthorityArbiter.Authority.NONE,"removed rejection authority");check(marker==ControlAuthorityArbiter.Authority.OFFENSIVE_COMBAT,"same UUID existing marker changed");System.out.println("classification=REMOVED_PENDING_REJECTED_MARKER_PRESERVED");return;}if(c.endsWith("-mob")){check(ReflectiveAircraft.writes.size()==2,"normal pending write");if(c.startsWith("combat-")){check(result==ControlAuthorityArbiter.Authority.OFFENSIVE_COMBAT,"combat authority");checkWrite(1,.2f,0f,.1f,.7f);}else{check(result==ControlAuthorityArbiter.Authority.FORMATION,"formation authority");checkWrite(1,.62f,0f,.02f,.08f);}return;}check(ReflectiveAircraft.writes.size()==1,"CONTRACT: no pending setter after pilot/side changes");boolean expectedPlayer=c.endsWith("-player")&&!c.endsWith("-removed-player")&&!c.endsWith("-client-player");check(result==(expectedPlayer?ControlAuthorityArbiter.Authority.PLAYER_CONTROLLED:ControlAuthorityArbiter.Authority.NONE),"rejected authority"); String policy=args[1];Object expected=(policy.equals("removed")||policy.equals("actual"))?ControlAuthorityArbiter.Authority.OFFENSIVE_COMBAT:(c.endsWith("-player")?ControlAuthorityArbiter.Authority.PLAYER_CONTROLLED:null);check(Objects.equals(marker,expected),"marker policy outcome");System.out.println("classification=NO_PENDING_WRITE_LABEL_IS_NOT_SUCCESS");}}
'''
CASES=('formation-mob','formation-player','formation-empty','formation-client','formation-terrain','formation-removed','formation-removed-only','formation-removed-player','formation-client-player','combat-mob','combat-player','combat-empty','combat-client','combat-removed','combat-removed-only','combat-removed-player','combat-client-player','risk','risk-only','direct','claimed')
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--policy',choices=('baseline','removed','actual'),required=True);p.add_argument('--expected-arbiter-sha256');p.add_argument('--java-home',type=pathlib.Path,required=True);p.add_argument('--dependencies-json',type=pathlib.Path,required=True);p.add_argument('--output',type=pathlib.Path,required=True);a=p.parse_args()

 if a.policy=='actual' and (not a.expected_arbiter_sha256 or len(a.expected_arbiter_sha256)!=64 or any(c not in '0123456789abcdef' for c in a.expected_arbiter_sha256)):
  p.error('actual mode requires a lowercase 64-character --expected-arbiter-sha256')
 out=a.output.absolute();out.mkdir(mode=0o700);src=out/'source-copy';fake=out/'stubs';classes=out/'classes';empty=out/'empty';[x.mkdir() for x in (src,fake,classes,empty)]
 jdk=a.java_home.resolve()/'bin';depsfile=a.dependencies_json.resolve();deps=[pathlib.Path(x) for x in json.loads(depsfile.read_text())]
 if not deps or any(not d.is_absolute() or not d.exists() for d in deps):raise ValueError('absolute existing classpath required')
 names=['ControlAuthorityArbiter','FormationFlightManager','AirspaceSafetyProbe','MobPilotGate','ControlOutcome','ControlProposal','FlightControlOutput','FlightPhase','AutopilotSession','FlightProfile','AutonomousFlightManager'];original=[ROOT/'com/wwdebug/autopilot'/(n+'.java') for n in names];copies=[]
 for source in original:
  text=source.read_text();modified=text
  if a.policy=='removed' and source.name=='ControlAuthorityArbiter.java':
   def once(text,old,new):
    if text.count(old)!=1:raise RuntimeError('candidate anchor mismatch '+repr(old))
    return text.replace(old,new)
   modified=once(modified,'    private static void write(Entity aircraft, ControlProposal proposal) {\n        ReflectiveAircraft.applyControl(aircraft, proposal.x(), proposal.y(), proposal.z(),\n                proposal.engineTarget());\n    }','    // True means the adapter was called, not that the native setters succeeded.\n    private static boolean attemptPendingWrite(Entity aircraft, ControlProposal proposal) {\n        if (aircraft.isRemoved() || aircraft.level().isClientSide || !MobPilotGate.isMobPiloted(aircraft)) {\n            return false;\n        }\n        ReflectiveAircraft.applyControl(aircraft, proposal.x(), proposal.y(), proposal.z(),\n                proposal.engineTarget());\n        return true;\n    }')
   modified=once(modified,'        Authority authority = decide(aircraft);\n        recordAuthorityChange(aircraft, authority);\n        return authority;','        PendingDecision decision = decide(aircraft);\n        if (decision.updateMarker()) {\n            recordAuthorityChange(aircraft, decision.authority());\n        }\n        return decision.authority();')
   modified=once(modified,'    private static Authority decide(Entity aircraft) {','    private record PendingDecision(Authority authority, boolean updateMarker) {\n    }\n\n    private static PendingDecision rejected(Entity aircraft) {\n        Authority label = !aircraft.isRemoved() && !aircraft.level().isClientSide\n                && MobPilotGate.isPlayerControlled(aircraft)\n                ? Authority.PLAYER_CONTROLLED : Authority.NONE;\n        return new PendingDecision(label, '+('true' if a.policy=='update' else 'false')+');\n    }\n\n    private static PendingDecision decide(Entity aircraft) {')
   left=modified.index('    private static PendingDecision decide(Entity aircraft) {');right=modified.index('    /**\n     * Records ownership',left);body=modified[left:right]
   for label in ['NONE','PLAYER_CONTROLLED','COLLISION_AVOIDANCE','TERRAIN_AVOIDANCE']:
    body=body.replace('return Authority.'+label+';', 'return new PendingDecision(Authority.'+label+', true);')
   body=once(body,'            combat.pendingWrite().ifPresent(proposal -> write(aircraft, proposal));\n            return combat.authority();','            if (combat.pendingWrite().isPresent()\n                    && !attemptPendingWrite(aircraft, combat.pendingWrite().get())) {\n                return rejected(aircraft);\n            }\n            return new PendingDecision(combat.authority(), true);')
   body=once(body,'            formation.pendingWrite().ifPresent(proposal -> write(aircraft, proposal));\n            return formation.authority();','            if (formation.pendingWrite().isPresent()\n                    && !attemptPendingWrite(aircraft, formation.pendingWrite().get())) {\n                return rejected(aircraft);\n            }\n            return new PendingDecision(formation.authority(), true);')
   body=once(body,'        return AutonomousFlightManager.status(aircraft.getUUID()).isPresent()\n                ? Authority.BASE_AUTONOMY : Authority.NONE;','        return new PendingDecision(AutonomousFlightManager.status(aircraft.getUUID()).isPresent()\n                ? Authority.BASE_AUTONOMY : Authority.NONE, true);')
   modified=modified[:left]+body+modified[right:]
  target=src/source.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(source.read_bytes()) if a.policy=='actual' else target.write_text(modified);copies.append(target)
  if modified!=text:(out/(source.stem+'.patch')).write_text(''.join(difflib.unified_diff(text.splitlines(True),modified.splitlines(True),fromfile='original/'+source.name,tofile='private-copy/'+source.name)))
 paths=[]
 for name,value in STUBS.items():
  target=fake/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(value);paths.append(target)
 def inventory(entries):
  result={}
  for entry in entries:
   files=sorted(p for p in entry.rglob('*') if p.is_file()) if entry.is_dir() else [entry]
   for item in files:result[str(item)]=digest(item)
  return result
 inputs=original+copies+paths+[jdk/'java',jdk/'javac',depsfile,pathlib.Path(__file__).resolve()];before=inventory(inputs);cpbefore=inventory(deps);shutil.copyfile(__file__,out/'runner-snapshot.py')
 copy_equal=all(digest(x)==digest(y) for x,y in zip(original,copies));patch_files=sorted(p.name for p in out.glob('*.patch'));arbiter_sha=digest(next(x for x in original if x.name=='ControlAuthorityArbiter.java'));actual_provenance=(a.policy!='actual' or (copy_equal and not patch_files and arbiter_sha==a.expected_arbiter_sha256))
 if not actual_provenance:raise RuntimeError('actual mode source, copy or patch provenance mismatch')
 report={'source_base':'4c04b12 with worktree edits when actual','mode':a.policy,'arbiter_sha256':arbiter_sha,'expected_arbiter_sha256':a.expected_arbiter_sha256,'source_copy_equal':copy_equal,'patch_files':patch_files,'actual_provenance':actual_provenance,'scope':('Private removed-guard source copies; ' if a.policy=='removed' else 'Private unmodified source copies from current worktree; ')+'artificial callbacks, fake aircraft/world/setter/combat/terrain; no runtime, native success, reentrancy or same-UUID safety claim. Authority labels are not setter success.','inputs_before':before,'classpath_before':cpbefore,'runs':{}}
 def run(name,command):
  result=subprocess.run(command,cwd=out,capture_output=True,text=True,timeout=30);(out/(name+'.stdout')).write_text(result.stdout);(out/(name+'.stderr')).write_text(result.stderr);report['runs'][name]={'argv':command,'exit':result.returncode};print(name,result.returncode,flush=True);return result.returncode
 rc=run('compile',[str(jdk/'javac'),'-proc:none','--release','17','-cp',os.pathsep.join(map(str,deps)),'-sourcepath',str(empty),'-d',str(classes),*map(str,copies),*map(str,paths)])
 if rc==0:
  for case in CASES:run(case,[str(jdk/'java'),'-Xmx128m','-Xverify:all','-Xlog:class+load=info:file='+str(out/(case+'.classes.log')),'-cp',str(classes)+os.pathsep+os.pathsep.join(map(str,deps)),'com.wwdebug.autopilot.Probe',case,a.policy])
 report['inputs_after']=inventory(inputs);report['inputs_unchanged']=before==report['inputs_after'];report['classpath_after']=inventory(deps);report['classpath_unchanged']=cpbefore==report['classpath_after'];report['compiled_classes']=inventory([classes]);report['runner_snapshot_sha256']=digest(out/'runner-snapshot.py');(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
 return 0 if actual_provenance and report['inputs_unchanged'] and report['classpath_unchanged'] and len(report['runs'])==len(CASES)+1 and all(x['exit']==0 for x in report['runs'].values()) else 1
if __name__=='__main__':sys.exit(main())
