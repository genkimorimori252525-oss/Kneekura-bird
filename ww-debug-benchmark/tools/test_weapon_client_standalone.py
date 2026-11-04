#!/usr/bin/env python3
"""Exercise real weapon policy with synthetic stand-ins; no Minecraft or Forge runs.

Optional WEAPON_CLASSES_DIR replaces classes with trusted local built bytes;
WEAPON_SOURCE_DIR selects source to compile and execute. Use only trusted inputs.
This executes supplied class files and source. Source and
class snapshots, stub code, runtime classpath, outputs and SHA-256 are recorded.
A passing result does not prove Minecraft runtime, target selection, native gun
behaviour, actual tick ordering, networking or player takeover.
"""
import hashlib
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SRC = Path(os.environ.get('WEAPON_SOURCE_DIR', ROOT / 'src/main/java/com/wwdebug/autopilot'))
NAMES = ('CombatWeaponManager.java', 'MobPilotGate.java', 'FlightPhase.java')
STUBS = {
'net/minecraft/world/phys/Vec3.java': '''
package net.minecraft.world.phys;
public class Vec3 {
 public final double x,y,z; public Vec3(double x,double y,double z){this.x=x;this.y=y;this.z=z;}
 public Vec3 add(Vec3 b){return new Vec3(x+b.x,y+b.y,z+b.z);} public Vec3 subtract(Vec3 b){return new Vec3(x-b.x,y-b.y,z-b.z);}
 public Vec3 scale(double s){return new Vec3(x*s,y*s,z*s);} public double dot(Vec3 b){return x*b.x+y*b.y+z*b.z;}
 public double lengthSqr(){return dot(this);} public double horizontalDistance(){return Math.sqrt(x*x+z*z);}
 public double distanceTo(Vec3 b){return Math.sqrt(subtract(b).lengthSqr());} public Vec3 normalize(){double l=Math.sqrt(lengthSqr());return l<1e-9?new Vec3(0,0,0):scale(1/l);}
}
''',
'net/minecraft/world/phys/AABB.java': '''
package net.minecraft.world.phys;
public class AABB { private Vec3 center; public AABB(Vec3 a,Vec3 b){center=a.add(b).scale(0.5);} public AABB inflate(double d){return this;} public Vec3 getCenter(){return center;} }
''',
'net/minecraft/world/phys/HitResult.java': '''
package net.minecraft.world.phys;
public class HitResult { public enum Type { MISS, BLOCK, ENTITY } }
''',
'net/minecraft/world/phys/BlockHitResult.java': '''
package net.minecraft.world.phys;
public class BlockHitResult extends HitResult { private final Type t; public BlockHitResult(Type t){this.t=t;} public Type getType(){return t;} }
''',
'net/minecraft/util/Mth.java': '''
package net.minecraft.util;
public class Mth {public static double clamp(double v,double min,double max){return Math.max(min,Math.min(max,v));}}
''',
'net/minecraft/world/level/ClipContext.java': '''
package net.minecraft.world.level;
import net.minecraft.world.entity.Entity; import net.minecraft.world.phys.Vec3;
public class ClipContext {public enum Block{COLLIDER} public enum Fluid{NONE} public ClipContext(Vec3 a,Vec3 b,Block c,Fluid d,Entity e){}}
''',
'net/minecraft/world/level/Level.java': '''
package net.minecraft.world.level;
import net.minecraft.world.phys.BlockHitResult; import net.minecraft.world.phys.HitResult;
public class Level { public boolean isClientSide; public boolean terrain; public Level(boolean client){isClientSide=client;}
 public BlockHitResult clip(ClipContext c){return new BlockHitResult(terrain?HitResult.Type.BLOCK:HitResult.Type.MISS);} }
''',
'net/minecraft/server/MinecraftServer.java': '''
package net.minecraft.server; public class MinecraftServer { }
''',
'net/minecraft/world/entity/EntityType.java': '''
package net.minecraft.world.entity; public class EntityType<T> { public String toString(){return "fixture";} }
''',
'net/minecraft/world/entity/Entity.java': '''
package net.minecraft.world.entity;
import java.util.UUID; import net.minecraft.world.level.Level; import net.minecraft.world.phys.*;
public class Entity {
 public UUID id=new UUID(0,1); public Level world; public LivingEntity pilot; public boolean airplane=true; public Vec3 position=new Vec3(0,0,0);
 public Entity(Level l){world=l;} public Level level(){return world;} public UUID getUUID(){return id;}
 public LivingEntity getControllingPassenger(){return pilot;} public AABB getBoundingBox(){return new AABB(position,position);}
 public Vec3 getLookAngle(){return new Vec3(1,0,0);} public Vec3 getDeltaMovement(){return new Vec3(0.1,0,0);}
 public boolean hasPassenger(Entity e){return e==pilot;} public boolean isAlliedTo(Entity e){return false;}
 public EntityType<?> getType(){return new EntityType<>();} public float getBbWidth(){return 1.0f;}
}
''',
'net/minecraft/world/entity/LivingEntity.java': '''
package net.minecraft.world.entity; import net.minecraft.world.level.Level; import net.minecraft.world.phys.Vec3;
public class LivingEntity extends Entity { public boolean alive=true; public LivingEntity(Level l){super(l);} public boolean isAlive(){return alive;} public Vec3 getEyePosition(){return position;} }
''',
'net/minecraft/world/entity/Mob.java': '''
package net.minecraft.world.entity; import net.minecraft.world.level.Level;
public class Mob extends LivingEntity {public Mob(Level l){super(l);} public LivingEntity getTarget(){return null;} }
''',
'net/minecraft/world/entity/TamableAnimal.java': '''
package net.minecraft.world.entity; import net.minecraft.world.level.Level;
public class TamableAnimal extends Mob {public TamableAnimal(Level l){super(l);} public boolean isTame(){return true;} }
''',
'net/minecraft/world/entity/player/Player.java': '''
package net.minecraft.world.entity.player; import net.minecraft.world.entity.LivingEntity; import net.minecraft.world.level.Level;
public class Player extends LivingEntity {public Player(Level l){super(l);} }
''',
'net/minecraft/world/entity/monster/Enemy.java': '''
package net.minecraft.world.entity.monster; public interface Enemy { }
''',
'net/minecraft/world/item/ItemStack.java': '''
package net.minecraft.world.item; public class ItemStack { }
''',
'net/minecraft/server/level/ServerLevel.java': '''
package net.minecraft.server.level;
import java.util.*; import java.util.function.Predicate; import net.minecraft.server.MinecraftServer; import net.minecraft.world.level.Level; import net.minecraft.world.entity.*; import net.minecraft.world.phys.AABB;
public class ServerLevel extends Level {public Entity target; public List<LivingEntity> candidates=new ArrayList<>(); public ServerLevel(){super(false);} public MinecraftServer getServer(){return null;}
 public Entity getEntity(UUID id){return target!=null && target.getUUID().equals(id)?target:null;}
 public <T extends Entity> List<T> getEntitiesOfClass(Class<T> c,AABB box,Predicate<? super T> test){List<T> out=new ArrayList<>();for(LivingEntity e:candidates)if(c.isInstance(e)&&test.test(c.cast(e)))out.add(c.cast(e));return out;}
}
''',
'com/wwdebug/benchmark/ReflectiveAircraft.java': '''
package com.wwdebug.benchmark; import net.minecraft.world.entity.Entity;
public class ReflectiveAircraft {public static boolean isAirplane(Entity e){return e.airplane;}}
''',
'com/wwdebug/benchmark/ReflectiveArmament.java': '''
package com.wwdebug.benchmark; import java.util.*; import net.minecraft.world.entity.Entity; import net.minecraft.world.item.ItemStack; import net.minecraft.world.phys.Vec3; import com.wwdebug.autopilot.WeaponProbe;
public class ReflectiveArmament {
 public record MountedWeapon(int slot,int index,int gunnerOffset,int loadedAmmo,ItemStack ammoStack,String className){}
 public record FireResult(boolean invoked,int loadedAmmoBefore,int loadedAmmoAfter,int reserveBefore,int reserveAfter,String reason){}
 public static List<MountedWeapon> machineGuns(Entity e){return List.of(new MountedWeapon(0,0,0,20,null,"synthetic"));}
 public static int estimatedShotsRemaining(Entity e){return WeaponProbe.ammo;} public static int reserveGunpowder(Entity e){return 0;}
 public static FireResult fire(Entity e,MountedWeapon w,Vec3 direction){WeaponProbe.fireCalls++;int before=WeaponProbe.ammo;if(WeaponProbe.consume)WeaponProbe.ammo--;return new FireResult(true,before,WeaponProbe.ammo,0,0,"fixture");}
}
''',
'com/wwdebug/autopilot/AutonomousFlightManager.java': '''
package com.wwdebug.autopilot; import java.util.*;
public class AutonomousFlightManager {
 public record SessionStatus(UUID aircraftUuid,String aircraftName,String profileId,String doctrine,FlightPhase phase,int phaseTicks,int missionTicks,String transitionReason){}
 public static Optional<SessionStatus> status(UUID id){return WeaponProbe.session?Optional.of(new SessionStatus(id,"a","p","d",WeaponProbe.phase,0,0,"fixture")):Optional.empty();}
}
''',
'com/wwdebug/autopilot/CombatTargetSelector.java': '''
package com.wwdebug.autopilot; import java.util.UUID; import net.minecraft.world.phys.Vec3;
public class CombatTargetSelector {
 public record Solution(UUID targetUuid,String targetType,String targetName,Vec3 aimPoint,Vec3 direction,double distanceBlocks,double angleOffNoseDeg,boolean lineOfSight,boolean attackingPilot,boolean explicitFactionHostile,String targetFaction,double score){public String description(){return "synthetic";}}
}
''',
'com/wwdebug/autopilot/CombatAwarenessManager.java': '''
package com.wwdebug.autopilot; import java.util.*;
public class CombatAwarenessManager {public static Optional<CombatTargetSelector.Solution> currentSolution(UUID id){return Optional.ofNullable(WeaponProbe.solution);}}
''',
'com/wwdebug/autopilot/AirCombatManeuverManager.java': '''
package com.wwdebug.autopilot; import java.util.*; import net.minecraft.world.phys.Vec3;
public class AirCombatManeuverManager {public record AimSolution(UUID targetUuid,Vec3 aimPoint,Vec3 direction,double distanceBlocks,double angleOffNoseDeg,double timeSeconds){} public static Optional<AimSolution> currentAim(UUID a,UUID b){return Optional.ofNullable(WeaponProbe.aim);}}
''',
'com/wwdebug/autopilot/CombatFactionRelations.java': '''
package com.wwdebug.autopilot; import net.minecraft.world.entity.*;
public class CombatFactionRelations {public static boolean protectedFromFire(Entity a,Entity p,Entity c){return false;}}
''',
'com/wwdebug/autopilot/AutopilotLogManager.java': '''
package com.wwdebug.autopilot; import net.minecraft.server.MinecraftServer; import net.minecraft.world.entity.Entity;
public class AutopilotLogManager {public static void writeEvent(MinecraftServer s,Entity e,String event,String detail,FlightPhase phase){WeaponProbe.logs++;WeaponProbe.lastLog=event+":"+detail;}}
''',
'com/wwdebug/autopilot/WeaponProbe.java': '''
package com.wwdebug.autopilot;
import java.lang.reflect.*; import java.util.*; import net.minecraft.world.entity.*; import net.minecraft.world.entity.player.Player; import net.minecraft.world.level.Level; import net.minecraft.server.level.ServerLevel; import net.minecraft.world.phys.Vec3;
public class WeaponProbe {
 public static int fireCalls, logs, ammo; public static boolean session,consume; public static String lastLog; public static FlightPhase phase;
 public static CombatTargetSelector.Solution solution; public static AirCombatManeuverManager.AimSolution aim; static int checks,failures; static final UUID TARGET=new UUID(0,2);
 static void check(boolean b,String name){checks++;if(!b){failures++;System.err.println("FAIL "+name);}else System.out.println("PASS "+name);}
 static Entity setup(){ServerLevel level=new ServerLevel();Entity aircraft=new Entity(level);aircraft.pilot=new Mob(level);LivingEntity target=new LivingEntity(level);target.id=TARGET;target.position=new Vec3(60,0,0);level.target=target;fireCalls=logs=0;ammo=100;session=true;consume=true;phase=FlightPhase.CRUISE_OUTBOUND;aim=null;lastLog="";solution=new CombatTargetSelector.Solution(TARGET,"target","target",target.position,new Vec3(1,0,0),60,0,true,false,true,"hostile",1);CombatWeaponManager.clear(aircraft.id);return aircraft;}
 static Object state(Entity a)throws Exception{Field f=CombatWeaponManager.class.getDeclaredField("STATES");f.setAccessible(true);return ((Map<?,?>)f.get(null)).get(a.id);}
 static String values(Object s)throws Exception{if(s==null)return "missing";StringBuilder b=new StringBuilder();for(String n:new String[]{"volleysRemaining","shotDelayTicks","cooldownTicks","lastInhibitReason","outOfAmmoLogged"}){Field f=s.getClass().getDeclaredField(n);f.setAccessible(true);b.append(n).append('=').append(f.get(s)).append(';');}return b.toString();}
 static CombatTargetSelector.Solution solution(double dist,double angle,boolean los){return new CombatTargetSelector.Solution(TARGET,"target","target",new Vec3(60,0,0),new Vec3(1,0,0),dist,angle,los,false,true,"hostile",1);}
 static void clearCase(String name,int mode)throws Exception{Entity a=setup();CombatWeaponManager.tick(a);check(state(a)!=null,name+" seeded");switch(mode){case 0:a.airplane=false;break;case 1:a.world=new Level(false);break;case 2:a.pilot=new Player(a.world);break;case 3:a.pilot=null;break;case 4:session=false;break;}CombatWeaponManager.tick(a);check(state(a)==null,name+" clear");check(fireCalls==1,name+" no extra fire");}
 static void inhibited(String name,int mode,String reason)throws Exception{Entity a=setup();ServerLevel l=(ServerLevel)a.world;switch(mode){case 0:solution=solution(60,0,false);break;case 1:l.terrain=true;break;case 2:solution=solution(17.9,0,true);break;case 3:solution=solution(135.1,0,true);break;case 4:solution=solution(60,46,true);aim=new AirCombatManeuverManager.AimSolution(TARGET,new Vec3(60,0,0),new Vec3(1,0,0),60,0,1);break;case 5:Player friend=new Player(l);friend.position=new Vec3(30,0,0);l.candidates.add(friend);break;case 6:phase=FlightPhase.FINAL;break;case 7:ammo=0;break;case 8:solution=solution(60,3.1,true);break;case 9:LivingEntity neutral=new LivingEntity(l);neutral.position=new Vec3(30,0,0);l.candidates.add(neutral);break;}CombatWeaponManager.tick(a);check(fireCalls==0,name+" no fire");check(lastLog!=null&&lastLog.contains(reason),name+" recorded "+reason);}
 public static void main(String[] args)throws Exception{
  Entity a=setup();CombatWeaponManager.tick(a);check(fireCalls==1,"server first volley");Object old=state(a);String oldValues=values(old);int oldLogs=logs;
  Entity client=new Entity(new Level(true));client.id=a.id;client.pilot=new Mob(client.world);CombatWeaponManager.tick(client);
  check(state(a)==old && old!=null,"client preserves server state identity");check(values(state(a)).equals(oldValues),"client preserves state fields");check(fireCalls==1 && logs==oldLogs,"client does not fire or log");
  for(int tick=1;tick<=22;tick++){CombatWeaponManager.tick(a);int expected=tick<4?1:tick<22?2:3;check(fireCalls==expected,"cadence tick "+tick+" calls="+fireCalls+" expected="+expected);}
  clearCase("non-airplane",0);clearCase("non-server level",1);clearCase("player pilot",2);clearCase("empty pilot",3);clearCase("missing session",4);
  String[] labels={"line of sight","terrain","short range","long range","raw rear angle despite lead","protected corridor","landing phase","empty ammo","nose cone","neutral corridor"};String[] reasons={"target_line_of_sight_blocked","immediate_terrain_conflict_has_priority","target_outside_machine_gun_range","target_outside_machine_gun_range","target_currently_outside_forward_gun_hemisphere","friendly_fire_corridor_blocked_by","weapons_disabled_in_flight_phase","weapon_out_of_ammo","target_outside_nose_firing_cone","friendly_fire_corridor_blocked_by"};for(int i=0;i<labels.length;i++)inhibited(labels[i],i,reasons[i]);
  Entity noConsumption=setup();consume=false;CombatWeaponManager.tick(noConsumption);check(fireCalls==1,"no consumption call observed");check(lastLog!=null&&lastLog.contains("weapon_api_invoked_without_ammunition_consumption"),"no consumption inhibited");
  System.out.println("RESULT checks="+checks+" failures="+failures+" scope=synthetic_standins");if(failures>0)System.exit(1);
 }
}
''',
}

def main():
    built = os.environ.get('WEAPON_CLASSES_DIR')
    print('test_sha256', hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), flush=True)
    print('scope=synthetic stand-ins; no Minecraft/Forge runtime, native armament or target selection', flush=True)
    print('mode=' + ('trusted built-class snapshot' if built else 'real source snapshot'), flush=True)
    with tempfile.TemporaryDirectory(prefix='weapon-client-test-') as tmp:
        root = Path(tmp); classes = root/'classes'; classes.mkdir(); empty=root/'empty';empty.mkdir(); sources=[]
        for name, data in STUBS.items():
            path=root/'stubs'/name;path.parent.mkdir(parents=True,exist_ok=True);raw=data.encode();path.write_bytes(raw);sources.append(path)
            print('stub_sha256',name,hashlib.sha256(raw).hexdigest(),flush=True)
        for name in NAMES:
            raw=(SRC/name).read_bytes(); path=root/'production-source'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw);sources.append(path)
            print('source_sha256',name,hashlib.sha256(raw).hexdigest(),flush=True)
        javac=os.environ.get('WEAPON_JAVAC','javac');java=os.environ.get('WEAPON_JAVA','java')
        for label, executable in (('javac', javac), ('java', java)):
            resolved = Path(shutil.which(executable) or executable).resolve(strict=True)
            print('executable_sha256', label, str(resolved), hashlib.sha256(resolved.read_bytes()).hexdigest(), flush=True)
        command=[javac,'--release','17','-proc:none','-classpath',str(classes),'-sourcepath',str(empty),'-d',str(classes),*map(str,sources)]
        print('compile',json.dumps(command),'runtime_classpath',str(classes),flush=True)
        result=subprocess.run(command,text=True,capture_output=True,check=False);print(result.stdout+result.stderr,end='',flush=True)
        if result.returncode:return result.returncode
        if built:
            relative=Path('com/wwdebug/autopilot')
            for name in ('CombatWeaponManager.class','CombatWeaponManager$State.class','MobPilotGate.class','FlightPhase.class','FlightPhase$1.class'):
                path=Path(built)/relative/name; raw=path.read_bytes(); (classes/relative/name).write_bytes(raw)
                print('built_class_sha256',name,hashlib.sha256(raw).hexdigest(),flush=True)
        for path in sorted(classes.rglob('*.class')):
            print('class_sha256', str(path.relative_to(classes)), hashlib.sha256(path.read_bytes()).hexdigest(), flush=True)
        run=[java,'-Xverify:all','-cp',str(classes),'com.wwdebug.autopilot.WeaponProbe']
        print('execute',json.dumps(run),flush=True);result=subprocess.run(run,text=True,capture_output=True,check=False)
        print(result.stdout+result.stderr,end='',flush=True);return result.returncode
if __name__=='__main__':sys.exit(main())
