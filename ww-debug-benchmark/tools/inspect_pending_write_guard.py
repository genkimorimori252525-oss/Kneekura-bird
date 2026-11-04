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
STUBS['com/wwdebug/autopilot/FighterCombatFacade.java'] = '''package com.wwdebug.autopilot;
import net.minecraft.world.entity.Entity; import net.minecraft.world.entity.player.Player; import com.wwdebug.benchmark.ReflectiveAircraft;
public class FighterCombatFacade {public static String mode="none"; public static ControlOutcome applyControl(Entity a,boolean risk){
 if(mode.equals("direct")){ReflectiveAircraft.applyControl(a,.2f,0f,.1f,.7f);return ControlOutcome.alreadyWrote(ControlAuthorityArbiter.Authority.OFFENSIVE_COMBAT);}
 if(risk)return ControlOutcome.none();
 if(mode.startsWith("formation-")||mode.startsWith("combat-")){AutopilotLogManager.events.add("callback:"+mode+":writes_before="+ReflectiveAircraft.writes.size());if(mode.endsWith("-player"))a.pilot=new Player();if(mode.endsWith("-empty"))a.pilot=null;if(mode.endsWith("-client"))a.level().isClientSide=true;if(mode.endsWith("-terrain")){TerrainAvoidancePlanner.enabled=true;TerrainAvoidancePlanner.marked=true;}if(mode.startsWith("combat-"))return ControlOutcome.proposed(ControlProposal.ofRawInputs(ControlAuthorityArbiter.Authority.OFFENSIVE_COMBAT,.2f,0f,.1f,.7f,"fixture-pending"));}return ControlOutcome.none();}}'''
STUBS['com/wwdebug/autopilot/Probe.java'] = '''package com.wwdebug.autopilot;
import java.util.*; import net.minecraft.server.level.ServerLevel; import net.minecraft.world.entity.*; import net.minecraft.world.phys.Vec3; import net.minecraft.resources.ResourceLocation; import com.wwdebug.benchmark.ReflectiveAircraft;
public class Probe {static FlightProfile profile=new FlightProfile(new ResourceLocation("fixture","a6m"),"fighter","fixture",10.273020653865627,32.723952272022544,22,34.644173364843915,null,null,50);
static void check(boolean b,String m){if(!b)throw new AssertionError(m);}static void checkWrite(int n,float x,float y,float z,float engine){String[] s=ReflectiveAircraft.writes.get(n).split(",");float[] w={x,y,z,engine};for(int i=0;i<4;i++){float v=Float.parseFloat(s[i]);check(Float.isFinite(v)&&Math.abs(v-w[i])<.0001f,"setter "+n+" field "+i);}}
public static void main(String[] args)throws Exception{String c=args[0];ServerLevel l=new ServerLevel();Entity a=new Entity(new UUID(0,2),l),leader=new Entity(new UUID(0,1),l);a.vel=new Vec3(0,0,30.779231357359148/20.);a.pilot=new Mob();leader.pilot=new Mob(new UUID(0,4));boolean risk=c.equals("risk")||c.equals("risk-only");leader.pos=risk?new Vec3(3,100,0):new Vec3(40,100,30);leader.vel=new Vec3(0,0,.75);leader.tags.add("wwformation:group:g");leader.tags.add("wwformation:leader");a.tags.add("wwformation:slot:1");a.tags.add("wwformation:group:g");l.entities.add(a);l.entities.add(leader);AutopilotValidationCheckpoint.ticks=c.equals("risk-only")?440:439;if(c.startsWith("formation-")||c.startsWith("combat-"))FighterCombatFacade.mode=c;if(c.equals("direct"))FighterCombatFacade.mode="direct";
var result=ControlAuthorityArbiter.applyControl(a);boolean observedRisk=AirspaceSafetyProbe.collisionRisk(a);var f=ControlAuthorityArbiter.class.getDeclaredField("LAST_AUTHORITY");f.setAccessible(true);Object marker=((Map<?,?>)f.get(null)).get(a.getUUID());System.out.println("case="+c+" authority="+result+" marker="+marker+" risk="+observedRisk+" pilot="+(a.pilot==null?"empty":a.pilot.getClass().getSimpleName())+" client="+a.level().isClientSide+" terrain="+TerrainAvoidancePlanner.marked);System.out.println("writes="+ReflectiveAircraft.writes);System.out.println("events="+AutopilotLogManager.events);System.out.println("adapters="+AutopilotLogManager.adapters);
check(!ReflectiveAircraft.writes.isEmpty(),"base call missing");checkWrite(0,-.35099998f,0f,-.15f,1f);if(c.equals("risk")){check(observedRisk&&result==ControlAuthorityArbiter.Authority.COLLISION_AVOIDANCE&&ReflectiveAircraft.writes.size()==2,"collision direct control");checkWrite(1,-.62f,0f,.1f,.28f);return;}if(c.equals("risk-only")){check(observedRisk&&result==ControlAuthorityArbiter.Authority.COLLISION_AVOIDANCE&&ReflectiveAircraft.writes.size()==1,"terminal risk only");return;}if(c.equals("direct")){check(result==ControlAuthorityArbiter.Authority.OFFENSIVE_COMBAT&&ReflectiveAircraft.writes.size()==2,"direct writer");checkWrite(1,.2f,0f,.1f,.7f);return;}check(!observedRisk,"unexpected collision risk");check(AutopilotLogManager.events.stream().anyMatch(e->e.startsWith("callback:"+c+":writes_before=1")),"callback must follow base");if(c.endsWith("-terrain")){check(result==ControlAuthorityArbiter.Authority.TERRAIN_AVOIDANCE&&ReflectiveAircraft.writes.size()==1,"terrain gate");return;}if(c.endsWith("-mob")){check(ReflectiveAircraft.writes.size()==2,"normal pending write");if(c.startsWith("combat-")){check(result==ControlAuthorityArbiter.Authority.OFFENSIVE_COMBAT,"combat authority");checkWrite(1,.2f,0f,.1f,.7f);}else{check(result==ControlAuthorityArbiter.Authority.FORMATION,"formation authority");checkWrite(1,.62f,0f,.02f,.08f);}return;}check(ReflectiveAircraft.writes.size()==1,"CONTRACT: no pending setter after pilot/side changes");check(result==(c.startsWith("combat-")?ControlAuthorityArbiter.Authority.OFFENSIVE_COMBAT:ControlAuthorityArbiter.Authority.FORMATION),"authority label changed");System.out.println("classification=NO_PENDING_WRITE_LABEL_IS_NOT_SUCCESS");}}
'''
CASES=('formation-mob','formation-player','formation-empty','formation-client','formation-terrain','combat-mob','combat-player','combat-empty','combat-client','risk','risk-only','direct')
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--guard',action='store_true');p.add_argument('--java-home',type=pathlib.Path,required=True);p.add_argument('--dependencies-json',type=pathlib.Path,required=True);p.add_argument('--output',type=pathlib.Path,required=True);a=p.parse_args()
 out=a.output.absolute();out.mkdir(mode=0o700);src=out/'source-copy';fake=out/'stubs';classes=out/'classes';empty=out/'empty';[x.mkdir() for x in (src,fake,classes,empty)]
 jdk=a.java_home.resolve()/'bin';depsfile=a.dependencies_json.resolve();deps=[pathlib.Path(x) for x in json.loads(depsfile.read_text())]
 if not deps or any(not d.is_absolute() or not d.exists() for d in deps):raise ValueError('absolute existing classpath required')
 names=['ControlAuthorityArbiter','FormationFlightManager','AirspaceSafetyProbe','MobPilotGate','ControlOutcome','ControlProposal','FlightControlOutput','FlightPhase','AutopilotSession','FlightProfile','AutonomousFlightManager'];original=[ROOT/'com/wwdebug/autopilot'/(n+'.java') for n in names];copies=[]
 for source in original:
  text=source.read_text();modified=text
  if a.guard and source.name=='ControlAuthorityArbiter.java':
   needle='    private static void write(Entity aircraft, ControlProposal proposal) {\n        ReflectiveAircraft.applyControl'
   replacement='    private static void write(Entity aircraft, ControlProposal proposal) {\n        if (aircraft.level().isClientSide || !MobPilotGate.isMobPiloted(aircraft)) {\n            return;\n        }\n        ReflectiveAircraft.applyControl'
   if text.count(needle)!=1:raise RuntimeError('guard anchor not unique')
   modified=text.replace(needle,replacement)
  target=src/source.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True);target.write_text(modified);copies.append(target)
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
 report={'source_base':'4c04b12','mode':'guard' if a.guard else 'baseline','scope':('Private guard-modified source copies; ' if a.guard else 'Private unmodified source copies; ')+'artificial callbacks, fake aircraft/world/setter/combat/terrain; no runtime, native success, reentrancy or same-UUID safety claim. Authority labels are not setter success.','inputs_before':before,'classpath_before':cpbefore,'runs':{}}
 def run(name,command):
  result=subprocess.run(command,cwd=out,capture_output=True,text=True,timeout=30);(out/(name+'.stdout')).write_text(result.stdout);(out/(name+'.stderr')).write_text(result.stderr);report['runs'][name]={'argv':command,'exit':result.returncode};print(name,result.returncode,flush=True);return result.returncode
 rc=run('compile',[str(jdk/'javac'),'-proc:none','--release','17','-cp',os.pathsep.join(map(str,deps)),'-sourcepath',str(empty),'-d',str(classes),*map(str,copies),*map(str,paths)])
 if rc==0:
  for case in CASES:run(case,[str(jdk/'java'),'-Xmx128m','-Xverify:all','-Xlog:class+load=info:file='+str(out/(case+'.classes.log')),'-cp',str(classes)+os.pathsep+os.pathsep.join(map(str,deps)),'com.wwdebug.autopilot.Probe',case])
 report['inputs_after']=inventory(inputs);report['inputs_unchanged']=before==report['inputs_after'];report['classpath_after']=inventory(deps);report['classpath_unchanged']=cpbefore==report['classpath_after'];report['compiled_classes']=inventory([classes]);report['runner_snapshot_sha256']=digest(out/'runner-snapshot.py');(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
 return 0 if report['inputs_unchanged'] and report['classpath_unchanged'] and len(report['runs'])==len(CASES)+1 and all(x['exit']==0 for x in report['runs'].values()) else 1
if __name__=='__main__':sys.exit(main())
