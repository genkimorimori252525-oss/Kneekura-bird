#!/usr/bin/env python3
"""Inspect unmodified defensive source with synthetic entities and deferred-write hook."""
import argparse,hashlib,json,os,pathlib,shutil,subprocess,sys
ROOT=pathlib.Path(__file__).resolve().parents[1]/"src/main/java"
STUBS = {'com/wwdebug/autopilot/AutopilotValidationCheckpoint.java': 'package com.wwdebug.autopilot; import java.util.UUID; '
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
STUBS['net/minecraft/world/entity/Entity.java']='''package net.minecraft.world.entity;
import java.util.*;import net.minecraft.world.phys.*;import net.minecraft.world.level.Level;
public class Entity {public UUID id;public Level world;public LivingEntity pilot;public boolean removed;public Vec3 pos=new Vec3(0,100,0),vel=new Vec3(0,0,.75);public Set<String> tags=new HashSet<>();public Entity(UUID u,Level l){id=u;world=l;}public UUID getUUID(){return id;}public net.minecraft.network.chat.Component getName(){return net.minecraft.network.chat.Component.literal("fixture");}public net.minecraft.server.MinecraftServer getServer(){return null;}public void setDeltaMovement(double x,double y,double z){vel=new Vec3(x,y,z);}public Level level(){return world;}public LivingEntity getControllingPassenger(){return pilot;}public boolean isRemoved(){com.wwdebug.autopilot.Probe.onRemovedGetter(this);return removed;}public boolean onGround(){return false;}public Vec3 position(){return pos;}public Vec3 getDeltaMovement(){return vel;}public Vec3 getLookAngle(){return new Vec3(0,0,1);}public float getYRot(){return 0;}public AABB getBoundingBox(){return new AABB(pos.x,pos.y,pos.z,pos.x+1,pos.y+1,pos.z+1);}public Set<String> getTags(){return tags;}}'''
STUBS['com/wwdebug/benchmark/ReflectiveAircraft.java']='''package com.wwdebug.benchmark;import java.util.*;import net.minecraft.world.entity.Entity;import com.wwdebug.autopilot.Probe;public class ReflectiveAircraft{public static List<String>writes=new ArrayList<>();public static List<Object>pilots=new ArrayList<>();public static boolean isAirplane(Entity e){return true;}public static boolean isControllable(Entity e){return true;}public static void applyControl(Entity e,float x,float y,float z,float engine){writes.add(x+","+y+","+z+","+engine);pilots.add(e.pilot);Probe.events.add("setter:"+writes.size()+":pilot="+(e.pilot==null?"empty":e.pilot.getUUID()));}}'''
STUBS['com/wwdebug/autopilot/FlightSnapshot.java']='''package com.wwdebug.autopilot;import net.minecraft.world.entity.Entity;import net.minecraft.world.phys.Vec3;public class FlightSnapshot{private final Entity a;public FlightSnapshot(Entity a){this.a=a;}public static FlightSnapshot capture(Entity a){return new FlightSnapshot(a);}public Vec3 position(){return a.position();}public Vec3 velocity(){return a.getDeltaMovement();}public Vec3 forward(){return a.getLookAngle();}public Vec3 horizontalForward(){return a.getLookAngle();}public Vec3 right(){return new Vec3(-1,0,0);}public double speedBps(){return a.getDeltaMovement().length()*20;}public double horizontalSpeedBps(){return a.getDeltaMovement().horizontalDistance()*20;}public double altitudeAboveGround(){return 100;}public boolean onGround(){return false;}public double verticalSpeedBps(){return 0;}public float yawDeg(){return 0;}public float pitchDeg(){return 0;}public double enginePower(){return .8;}public double engineTarget(){return .5;}public double movementYawDeg(){return 0;}public String movementDirection(){return "south";}}'''
STUBS['com/wwdebug/autopilot/AutopilotProfileRegistry.java']='''package com.wwdebug.autopilot;import java.util.*;import net.minecraft.world.entity.Entity;import net.minecraft.server.MinecraftServer;public class AutopilotProfileRegistry{public static Optional<FlightProfile> resolve(MinecraftServer s,Entity a){return Optional.of(Probe.profile);}public static String sourceDescription(){return "fixture";}}'''
STUBS['com/wwdebug/autopilot/AutopilotLogManager.java']='''package com.wwdebug.autopilot;import java.util.*;import com.google.gson.JsonObject;import net.minecraft.server.MinecraftServer;import net.minecraft.world.entity.Entity;public class AutopilotLogManager{public static List<String>frames=new ArrayList<>(),adapters=new ArrayList<>(),events=new ArrayList<>();public static void writeEvent(MinecraftServer s,Entity e,String t,String r,FlightPhase p){events.add(t+":"+r);Probe.events.add("log:"+t);if(t.equals("defensive_air_combat_clear")&&Probe.restoreOnClear)Probe.restoreDefensiveState(e);}public static void closeAircraft(MinecraftServer s,Entity e,FlightPhase p,String r){}public static void closeServer(MinecraftServer s){}public static void writeFrame(MinecraftServer s,Entity e,JsonObject f){frames.add(f.toString());}public static void writeControlAdapter(MinecraftServer s,Entity e,FlightPhase p,String r,FlightSnapshot f,FlightControlOutput b,FlightControlOutput a){adapters.add(r+":"+a.reason());Probe.events.add("adapter:"+a.reason());}}'''
STUBS['com/wwdebug/autopilot/CombatTargetSelector.java']='''package com.wwdebug.autopilot;import java.util.UUID;public class CombatTargetSelector{public record Solution(UUID targetUuid,double angleOffNoseDeg,boolean lineOfSight){}}'''
STUBS['com/wwdebug/autopilot/CombatAwarenessManager.java']='''package com.wwdebug.autopilot;import java.util.*;import net.minecraft.world.entity.Entity;public class CombatAwarenessManager{public static Optional<CombatTargetSelector.Solution> currentSolution(UUID id){return !Probe.noThreat&&id.equals(Probe.attackerId)?Optional.of(new CombatTargetSelector.Solution(Probe.pilotA.getUUID(),2,true)):Optional.empty();}public static void tick(Entity e){}public static void clear(UUID id){}}'''
STUBS['com/wwdebug/autopilot/CombatWeaponManager.java']='''package com.wwdebug.autopilot;import java.util.UUID;import net.minecraft.world.entity.Entity;public class CombatWeaponManager{public static int tickCalls;public static void tick(Entity e){tickCalls++;}public static void clear(UUID id){}}'''
STUBS['com/wwdebug/autopilot/AirCombatManeuverManager.java']='''package com.wwdebug.autopilot;import java.util.*;import net.minecraft.world.entity.Entity;public class AirCombatManeuverManager{public record AimSolution(double angleOffNoseDeg){} public static Optional<AimSolution> currentAim(UUID a,UUID b){return Optional.empty();}public static Optional<ControlProposal> applyControl(Entity e){Probe.offensiveCalls++;return Probe.offensive?Optional.of(ControlProposal.ofRawInputs(ControlAuthorityArbiter.Authority.OFFENSIVE_COMBAT,.2f,0f,.1f,.7f,"fake-offensive")):Optional.empty();}public static void clear(UUID id){}}'''
STUBS['com/wwdebug/autopilot/EnergyFighterApexYawAdapter.java']='''package com.wwdebug.autopilot;import java.util.*;import net.minecraft.world.entity.Entity;public class EnergyFighterApexYawAdapter{public static Optional<ControlProposal> applyControl(Entity e){Probe.energyCalls++;if(Probe.energyDirect){com.wwdebug.benchmark.ReflectiveAircraft.applyControl(e,.31f,0f,.11f,.81f);return Optional.empty();}return Probe.energy?Optional.of(ControlProposal.ofRawInputs(ControlAuthorityArbiter.Authority.ENERGY_FIGHTER_REENGAGEMENT,.3f,0f,.1f,.8f,"fake-energy")):Optional.empty();}public static boolean active(Entity e){return Probe.energyClaim||Probe.energyDirect;}}'''
STUBS['com/wwdebug/autopilot/Probe.java']='''package com.wwdebug.autopilot;
import java.util.*;import net.minecraft.server.level.ServerLevel;import net.minecraft.world.entity.*;import net.minecraft.world.entity.player.Player;import net.minecraft.world.phys.Vec3;import net.minecraft.resources.ResourceLocation;import com.wwdebug.benchmark.ReflectiveAircraft;
public class Probe{
 public static List<String>events=new ArrayList<>();public static UUID attackerId=new UUID(0,1);public static Mob pilotA,pilotB,pilotSame;public static Entity target;public static boolean noThreat,offensive,energy,energyClaim,energyDirect,hookFired,restoreOnClear;public static Object savedDefensiveState;public static int offensiveCalls,energyCalls;public static String scenario;
 static FlightProfile profile=new FlightProfile(new ResourceLocation("fixture","a6m"),"fighter","fixture",10.273020653865627,32.723952272022544,22,34.644173364843915,null,null,50);
 static void check(boolean b,String m){if(!b)throw new AssertionError(m);}
 public static void onRemovedGetter(Entity e){if(e!=target||hookFired||!scenario.startsWith("defense-")||scenario.equals("defense-claimed"))return;boolean inside=false;for(StackTraceElement f:Thread.currentThread().getStackTrace())if(f.getClassName().equals("com.wwdebug.autopilot.ControlAuthorityArbiter")&&f.getMethodName().equals("attemptPendingWrite"))inside=true;if(!inside)return;check(e.pilot==pilotA,"pre-hook pilot not A");check(AutopilotLogManager.adapters.stream().anyMatch(x->x.contains("defensive_")),"real defensive adapter missing before hook");hookFired=true;events.add("hook:pending-guard:pilot-A:after-defensive-adapter:writes="+ReflectiveAircraft.writes.size());switch(scenario){case "defense-swap"->e.pilot=pilotB;case "defense-same-uuid"->e.pilot=pilotSame;case "defense-same"->e.pilot=pilotA;case "defense-player"->e.pilot=new Player();case "defense-empty"->e.pilot=null;case "defense-client"->e.level().isClientSide=true;case "defense-removed"->e.removed=true;default->throw new AssertionError("unknown hook mode");}}
 @SuppressWarnings("unchecked") public static void restoreDefensiveState(Entity e){try{var f=DefensiveAirCombatManager.class.getDeclaredField("STATES");f.setAccessible(true);((Map<UUID,Object>)f.get(null)).put(e.getUUID(),savedDefensiveState);events.add("FAKE_REENTRY:restore-defensive-state");}catch(ReflectiveOperationException ex){throw new IllegalStateException(ex);}}
 public static void main(String[]args)throws Exception{scenario=args[0];ServerLevel l=new ServerLevel();Entity a=new Entity(new UUID(0,2),l),attacker=new Entity(attackerId,l);target=a;pilotA=new Mob(new UUID(0,3));pilotB=new Mob(new UUID(0,5));pilotSame=new Mob(new UUID(0,3));check(pilotA!=pilotB&&!pilotA.getUUID().equals(pilotB.getUUID()),"distinct pilot seed");check(pilotA!=pilotSame&&pilotA.getUUID().equals(pilotSame.getUUID()),"same UUID distinct object seed");a.pilot=pilotA;a.vel=new Vec3(0,0,30.779231357359148/20.);attacker.pilot=new Mob(new UUID(0,4));attacker.pos=scenario.equals("collision")||scenario.equals("risk-only")?new Vec3(3,100,0):new Vec3(0,100,-50);attacker.vel=new Vec3(0,0,.75);l.entities.add(a);l.entities.add(attacker);AutopilotValidationCheckpoint.ticks=scenario.equals("risk-only")?440:100;noThreat=scenario.equals("offensive");offensive=noThreat;energy=scenario.equals("energy");energyClaim=scenario.equals("energy-claimed");energyDirect=scenario.equals("energy-direct");if(scenario.equals("terrain"))TerrainAvoidancePlanner.enabled=true;if(scenario.equals("initial-player"))a.pilot=new Player();if(scenario.equals("initial-empty"))a.pilot=null;if(scenario.equals("initial-client"))l.isClientSide=true;
 var field=ControlAuthorityArbiter.class.getDeclaredField("LAST_AUTHORITY");field.setAccessible(true);@SuppressWarnings("unchecked") Map<UUID,ControlAuthorityArbiter.Authority> markers=(Map<UUID,ControlAuthorityArbiter.Authority>)field.get(null);UUID alias=new UUID(a.getUUID().getMostSignificantBits(),a.getUUID().getLeastSignificantBits());check(alias!=a.getUUID()&&alias.equals(a.getUUID()),"alias UUID ref");markers.put(alias,ControlAuthorityArbiter.Authority.ENERGY_FIGHTER_REENGAGEMENT);UUID other=new UUID(0,777);markers.put(other,ControlAuthorityArbiter.Authority.ENERGY_FIGHTER_REENGAGEMENT);
 if(scenario.equals("defense-claimed")){var setup=ControlAuthorityArbiter.applyControl(a);check(setup==ControlAuthorityArbiter.Authority.DEFENSIVE_COMBAT,"setup defensive");var sf=DefensiveAirCombatManager.class.getDeclaredField("STATES");sf.setAccessible(true);savedDefensiveState=((Map<?,?>)sf.get(null)).get(a.getUUID());check(savedDefensiveState!=null,"setup state missing");ReflectiveAircraft.writes.clear();ReflectiveAircraft.pilots.clear();events.clear();AutopilotLogManager.adapters.clear();AutopilotLogManager.events.clear();noThreat=true;restoreOnClear=true;markers.put(alias,ControlAuthorityArbiter.Authority.ENERGY_FIGHTER_REENGAGEMENT);}
 var authority=ControlAuthorityArbiter.applyControl(a);System.out.println("case="+scenario+" defensive_active="+DefensiveAirCombatManager.active(a)+" authority="+authority+" hook="+hookFired+" marker="+markers.get(a.getUUID())+" other_marker="+markers.get(other)+" pilot_is_A="+(a.pilot==pilotA)+" pilot_is_B="+(a.pilot==pilotB)+" pilot_is_same_uuid_B="+(a.pilot==pilotSame)+" writes="+ReflectiveAircraft.writes+" second_setter_is_A="+(ReflectiveAircraft.pilots.size()>1&&ReflectiveAircraft.pilots.get(1)==pilotA)+" second_setter_is_B="+(ReflectiveAircraft.pilots.size()>1&&ReflectiveAircraft.pilots.get(1)==pilotB)+" second_setter_is_same_uuid_B="+(ReflectiveAircraft.pilots.size()>1&&ReflectiveAircraft.pilots.get(1)==pilotSame)+" energy_calls="+energyCalls+" offensive_calls="+offensiveCalls+" fake_weapon_tick_calls="+CombatWeaponManager.tickCalls);System.out.println("events="+events);System.out.println("adapters="+AutopilotLogManager.adapters);System.out.println("log_events="+AutopilotLogManager.events);
 check(markers.get(other)==ControlAuthorityArbiter.Authority.ENERGY_FIGHTER_REENGAGEMENT,"other UUID marker");check(CombatWeaponManager.tickCalls==0,"weapon unexpectedly ticked");
 if(scenario.startsWith("initial-")){check(ReflectiveAircraft.writes.isEmpty(),"initial non-mob/client write");return;}check(ReflectiveAircraft.writes.size()>=1&&ReflectiveAircraft.pilots.get(0)==pilotA,"base setter A missing");
 if(scenario.equals("defense-claimed")){check(authority==ControlAuthorityArbiter.Authority.DEFENSIVE_COMBAT&&ReflectiveAircraft.writes.size()==1&&DefensiveAirCombatManager.active(a)&&offensiveCalls==0&&events.contains("FAKE_REENTRY:restore-defensive-state"),"artificial defensive claimed no proposal");System.out.println("classification=FAKE_REENTRY_DEFENSIVE_CLAIM_NOT_RUNTIME");return;}
 if(scenario.equals("defense-swap")||scenario.equals("defense-same-uuid")){check(hookFired,"proposal-stage hook missing");Object b=scenario.endsWith("same-uuid")?pilotSame:pilotB;check(a.pilot==b,"B not controlling");if(ReflectiveAircraft.pilots.size()>1)check(ReflectiveAircraft.pilots.get(1)==b,"second setter not B");check(ReflectiveAircraft.writes.size()==1,"CONTRACT: no stale defensive pending after pilot swap");return;}
 if(scenario.equals("defense-same")){check(hookFired&&a.pilot==pilotA&&authority==ControlAuthorityArbiter.Authority.DEFENSIVE_COMBAT&&ReflectiveAircraft.writes.size()==2&&ReflectiveAircraft.pilots.get(1)==pilotA,"same A defensive pending");return;}
 if(scenario.startsWith("defense-")){check(hookFired&&ReflectiveAircraft.writes.size()==1,"existing #209 pending gate");check(markers.get(a.getUUID())==ControlAuthorityArbiter.Authority.ENERGY_FIGHTER_REENGAGEMENT,"rejected marker changed");return;}
 if(scenario.equals("collision")){check(authority==ControlAuthorityArbiter.Authority.COLLISION_AVOIDANCE&&ReflectiveAircraft.writes.size()==2,"collision direct");return;}
 if(scenario.equals("risk-only")){check(authority==ControlAuthorityArbiter.Authority.COLLISION_AVOIDANCE&&ReflectiveAircraft.writes.size()==1,"risk-only");return;}
 if(scenario.equals("terrain")){check(authority==ControlAuthorityArbiter.Authority.TERRAIN_AVOIDANCE&&ReflectiveAircraft.writes.size()==1,"terrain");return;}
 if(scenario.equals("offensive")){check(authority==ControlAuthorityArbiter.Authority.OFFENSIVE_COMBAT&&ReflectiveAircraft.writes.size()==2&&offensiveCalls==1,"fake offensive control");return;}
 if(scenario.equals("energy")){check(authority==ControlAuthorityArbiter.Authority.ENERGY_FIGHTER_REENGAGEMENT&&ReflectiveAircraft.writes.size()==2&&offensiveCalls==0,"energy proposal priority");return;}
 if(scenario.equals("energy-claimed")){check(authority==ControlAuthorityArbiter.Authority.ENERGY_FIGHTER_REENGAGEMENT&&ReflectiveAircraft.writes.size()==1&&offensiveCalls==0,"energy claim priority");return;}
 if(scenario.equals("energy-direct")){check(authority==ControlAuthorityArbiter.Authority.ENERGY_FIGHTER_REENGAGEMENT&&ReflectiveAircraft.writes.size()==2&&offensiveCalls==0,"fake energy direct");return;}
 throw new AssertionError("unknown scenario");}
}'''
CASES=('defense-swap','defense-same-uuid','defense-same','defense-claimed','defense-player','defense-empty','defense-client','defense-removed','initial-player','initial-empty','initial-client','terrain','collision','risk-only','offensive','energy','energy-claimed','energy-direct')
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--java-home',type=pathlib.Path,required=True);p.add_argument('--dependencies-json',type=pathlib.Path,required=True);p.add_argument('--output',type=pathlib.Path,required=True);a=p.parse_args()
 out=a.output.absolute();out.mkdir(mode=0o700);src=out/'source-copy';fake=out/'stubs';classes=out/'classes';empty=out/'empty';[x.mkdir() for x in (src,fake,classes,empty)]
 jdk=a.java_home.resolve()/'bin';depsfile=a.dependencies_json.resolve();deps=[pathlib.Path(x) for x in json.loads(depsfile.read_text())]
 if not deps or any(not d.is_absolute() or not d.exists() for d in deps):raise ValueError('absolute existing classpath required')
 names=['ControlAuthorityArbiter','FormationFlightManager','AirspaceSafetyProbe','MobPilotGate','ControlOutcome','ControlProposal','FlightControlOutput','FlightPhase','AutopilotSession','FlightProfile','AutonomousFlightManager','FighterCombatFacade','DefensiveAirCombatManager','DefensiveAirCombatAction'];original=[ROOT/'com/wwdebug/autopilot'/(n+'.java') for n in names];copies=[]
 for source in original:
  target=src/source.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(source.read_bytes());copies.append(target)
 paths=[]
 for name,value in STUBS.items():
  target=fake/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(value);paths.append(target)
 def inventory(entries):
  result={}
  for entry in entries:
   files=sorted(p for p in entry.rglob('*') if p.is_file()) if entry.is_dir() else [entry]
   for item in files:result[str(item)]=digest(item)
  return result
 inputs=original+copies+paths+[jdk/'java',jdk/'javac',depsfile,pathlib.Path(__file__).resolve()];before=inventory(inputs);cpbefore=inventory(deps);shutil.copyfile(__file__,out/'runner-snapshot.py');copy_equal=all(digest(x)==digest(y) for x,y in zip(original,copies));arbiter=digest(next(x for x in original if x.name=='ControlAuthorityArbiter.java'));patches=sorted(p.name for p in out.glob('*.patch'))
 if not copy_equal or arbiter!='090110ff9896c5020efc0a47056063f1e10dfdf57c706b2273cd29a470bc8a3f' or patches:raise RuntimeError('source/copy/patch provenance mismatch')
 report={'scope':'Unmodified #214 source copies; fake Entity.isRemoved callback only in pending-write guard; fake awareness, snapshot, terrain, combat neighbours, setter and world. No runtime, fire, ownership or physical safety proof.','arbiter_sha256':arbiter,'source_copy_equal':copy_equal,'patch_files':patches,'inputs_before':before,'classpath_before':cpbefore,'runs':{}}
 def run(name,command):
  r=subprocess.run(command,cwd=out,capture_output=True,text=True,timeout=30);(out/(name+'.stdout')).write_text(r.stdout);(out/(name+'.stderr')).write_text(r.stderr);report['runs'][name]={'argv':command,'exit':r.returncode};print(name,r.returncode,flush=True);return r.returncode
 rc=run('compile',[str(jdk/'javac'),'-proc:none','--release','17','-cp',os.pathsep.join(map(str,deps)),'-sourcepath',str(empty),'-d',str(classes),*map(str,copies),*map(str,paths)])
 if rc==0:
  for case in CASES:run(case,[str(jdk/'java'),'-Xmx128m','-Xverify:all','-Xlog:class+load=info:file='+str(out/(case+'.classes.log')),'-cp',str(classes)+os.pathsep+os.pathsep.join(map(str,deps)),'com.wwdebug.autopilot.Probe',case])
 report['inputs_after']=inventory(inputs);report['inputs_unchanged']=before==report['inputs_after'];report['classpath_after']=inventory(deps);report['classpath_unchanged']=cpbefore==report['classpath_after'];report['compiled_classes']=inventory([classes]);report['runner_snapshot_sha256']=digest(out/'runner-snapshot.py');(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
 return 0 if report['inputs_unchanged'] and report['classpath_unchanged'] and len(report['runs'])==len(CASES)+1 and all(x['exit']==0 for x in report['runs'].values()) else 1
if __name__=='__main__':sys.exit(main())
