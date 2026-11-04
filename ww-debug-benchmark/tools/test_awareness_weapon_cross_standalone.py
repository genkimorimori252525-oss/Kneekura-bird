#!/usr/bin/env python3
"""Run real awareness and weapon managers together against isolated stand-ins.

The fixture reuses the repository's weapon-test fake physics/target/armament. It does
not run Minecraft/Forge, prove native firing, logical-side sharing or scene cleanup.
Only execute trusted local build classes. Existing weapon safety thresholds are unmodified.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
WEAPON_TEST=HERE/'test_weapon_client_standalone.py'
spec=importlib.util.spec_from_file_location('weapon_fixture',WEAPON_TEST)
weapon=importlib.util.module_from_spec(spec)
spec.loader.exec_module(weapon)
STUBS=dict(weapon.STUBS)
del STUBS['com/wwdebug/autopilot/CombatAwarenessManager.java']
selector='com/wwdebug/autopilot/CombatTargetSelector.java'
needle=' public record Solution('
assert STUBS[selector].count(needle)==1
STUBS[selector]=STUBS[selector].replace(needle, '''
 public static class State {private java.util.UUID targetUuid=new java.util.UUID(0,2);private int rescanTicks=7,lostTicks=3;}
 public record Update(java.util.Optional<Solution> solution,boolean acquiredOrChanged,boolean lost,String reason){}
 public static Update update(net.minecraft.server.level.ServerLevel l,net.minecraft.world.entity.Entity e,FlightPhase p,State s){
  CrossTracker.selectorTicks++;return new Update(java.util.Optional.ofNullable(WeaponProbe.solution),false,false,"fixture");
 }
 public record Solution(''')
air='com/wwdebug/autopilot/AirCombatManeuverManager.java'
needle='public class AirCombatManeuverManager {'
assert STUBS[air].count(needle)==1
STUBS[air]=STUBS[air].replace(needle,needle+' public static void clear(UUID id){CrossTracker.clearCalls++;}')
STUBS.update({
 'com/wwdebug/autopilot/CrossTracker.java': '''
package com.wwdebug.autopilot;
public class CrossTracker {public static boolean scene=true,marker=true;public static int clearCalls,sceneTicks,selectorTicks;}
''',
 'com/wwdebug/autopilot/CombatValidationSceneManager.java': '''
package com.wwdebug.autopilot;
import java.util.UUID; import net.minecraft.server.level.ServerLevel; import net.minecraft.world.entity.Entity;
public class CombatValidationSceneManager {public static void tick(ServerLevel l,Entity e){CrossTracker.sceneTicks++;} public static void clear(UUID id){CrossTracker.clearCalls++;}}
''',
 'com/wwdebug/autopilot/AirCombatValidationSceneManager.java': '''
package com.wwdebug.autopilot;
import java.util.UUID; import net.minecraft.server.level.ServerLevel; import net.minecraft.world.entity.Entity;
public class AirCombatValidationSceneManager {public static void tick(ServerLevel l,Entity e,FlightPhase p){CrossTracker.sceneTicks++;} public static void clear(UUID id){CrossTracker.clearCalls++;}}
''',
 'com/wwdebug/autopilot/MutualDogfightValidationManager.java': '''
package com.wwdebug.autopilot;
import java.util.UUID; import net.minecraft.server.level.ServerLevel; import net.minecraft.world.entity.Entity;
public class MutualDogfightValidationManager {public static void tick(ServerLevel l,Entity e,FlightPhase p){CrossTracker.sceneTicks++;} public static void clear(UUID id){CrossTracker.clearCalls++;CrossTracker.scene=false;}}
''',
 'com/wwdebug/autopilot/MutualDogfightOpeningAdapter.java': '''
package com.wwdebug.autopilot;
import java.util.UUID; import net.minecraft.server.level.ServerLevel; import net.minecraft.world.entity.Entity;
public class MutualDogfightOpeningAdapter {public static void apply(ServerLevel l,Entity e,FlightPhase p){CrossTracker.sceneTicks++;} public static void clear(UUID id){CrossTracker.clearCalls++;CrossTracker.marker=false;}}
''',
 'com/wwdebug/autopilot/IntegrationProbe.java': '''
package com.wwdebug.autopilot;
import java.lang.reflect.Field; import java.util.*;
import net.minecraft.server.level.ServerLevel; import net.minecraft.world.entity.*;
import net.minecraft.world.entity.player.Player; import net.minecraft.world.level.Level; import net.minecraft.world.phys.Vec3;
public class IntegrationProbe {
 public static void main(String[] args)throws Exception {
  String c=args[0]; Entity server=WeaponProbe.setup();
  CombatAwarenessManager.clear(server.id);CrossTracker.scene=true;CrossTracker.marker=true;
  CrossTracker.clearCalls=CrossTracker.sceneTicks=CrossTracker.selectorTicks=0;
  CombatAwarenessManager.tick(server);CombatWeaponManager.tick(server);
  check(WeaponProbe.fireCalls==1 && WeaponProbe.ammo==99,"server initial fake volley not observed");
  Map<UUID,Object> states=map(CombatAwarenessManager.class,"STATES"),solutions=map(CombatAwarenessManager.class,"SOLUTIONS");
  Object a=states.get(server.id),s=solutions.get(server.id),w=WeaponProbe.state(server);
  check(a!=null && s==WeaponProbe.solution && w!=null && CrossTracker.scene && CrossTracker.marker,"server initialization incomplete");
  String awarenessFields=awarenessValues(a),fields=WeaponProbe.values(w);int fire=WeaponProbe.fireCalls,ammo=WeaponProbe.ammo,logs=WeaponProbe.logs;
  int clears=CrossTracker.clearCalls,sceneTicks=CrossTracker.sceneTicks,selectorTicks=CrossTracker.selectorTicks;
  Entity client=new Entity(new Level(true));client.id=server.id;
  client.pilot=c.equals("client-player")?new Player(client.world):new Mob(client.world);
  check(client!=server && client.id.equals(server.id),"fixture entities must share only UUID");
  boolean weaponFirst=c.equals("weapon-first");
  for(int i=0;i<2;i++){
   boolean weapon=(i==0)==weaponFirst;
   if(weapon)CombatWeaponManager.tick(client);else CombatAwarenessManager.tick(client);
   check(states.get(server.id)==a && awarenessValues(a).equals(awarenessFields) && solutions.get(server.id)==s && WeaponProbe.state(server)==w
     && WeaponProbe.values(w).equals(fields) && WeaponProbe.fireCalls==fire && WeaponProbe.ammo==ammo
     && WeaponProbe.logs==logs && CrossTracker.scene && CrossTracker.marker && CrossTracker.clearCalls==clears
     && CrossTracker.sceneTicks==sceneTicks && CrossTracker.selectorTicks==selectorTicks,
     "CONTRACT_FAIL client "+(weapon?"weapon":"awareness")+" changed server fake state; a="+(states.get(server.id)==a)
       +" s="+(solutions.get(server.id)==s)+" w="+(WeaponProbe.state(server)==w)+" values="+WeaponProbe.values(WeaponProbe.state(server))
       +" scene="+CrossTracker.scene+" marker="+CrossTracker.marker+" fire="+WeaponProbe.fireCalls+" logs="+WeaponProbe.logs);
  }
  if(c.equals("awareness-first") || c.equals("weapon-first") || c.equals("client-player")){
   for(int tick=1;tick<=22;tick++){
    CombatAwarenessManager.tick(server);CombatWeaponManager.tick(server);
    int expected=tick<4?1:tick<22?2:3;
    check(WeaponProbe.fireCalls==expected,"server fake volley cadence tick="+tick+" actual="+WeaponProbe.fireCalls);
   }
  } else if(c.equals("player") || c.equals("empty") || c.equals("no-session")){
   if(c.equals("player"))server.pilot=new Player(server.world);else if(c.equals("empty"))server.pilot=null;else WeaponProbe.session=false;
   CombatAwarenessManager.tick(server);CombatWeaponManager.tick(server);
   check(WeaponProbe.fireCalls==fire && WeaponProbe.state(server)==null,"server gate failed to clear existing weapon state");
  } else {
   ServerLevel level=(ServerLevel)server.world;String reason;
   switch(c){
    case "no-target" -> {WeaponProbe.solution=null;reason="no_hostile_target";}
    case "los" -> {WeaponProbe.solution=WeaponProbe.solution(60,0,false);reason="target_line_of_sight_blocked";}
    case "terrain" -> {level.terrain=true;reason="immediate_terrain_conflict_has_priority";}
    case "rear" -> {WeaponProbe.solution=WeaponProbe.solution(60,46,true);WeaponProbe.aim=new AirCombatManeuverManager.AimSolution(WeaponProbe.TARGET,new Vec3(60,0,0),new Vec3(1,0,0),60,0,1);reason="target_currently_outside_forward_gun_hemisphere";}
    case "friendly" -> {Player friend=new Player(level);friend.position=new Vec3(30,0,0);level.candidates.add(friend);reason="friendly_fire_corridor_blocked_by";}
    default -> throw new AssertionError("unknown "+c);
   }
   CombatAwarenessManager.tick(server);CombatWeaponManager.tick(server);
   check(WeaponProbe.fireCalls==fire && WeaponProbe.lastLog!=null && WeaponProbe.lastLog.contains(reason),"server safety inhibition missing: "+reason+" log="+WeaponProbe.lastLog);
  }
  System.out.println("PASS "+c+" scope=synthetic_standins fire="+WeaponProbe.fireCalls+" ammo="+WeaponProbe.ammo+" scene="+CrossTracker.scene+" marker="+CrossTracker.marker);
 }
 private static String awarenessValues(Object state)throws Exception{
  StringBuilder b=new StringBuilder();for(String name:new String[]{"targetUuid","rescanTicks","lostTicks"}){
   Field f=state.getClass().getDeclaredField(name);f.setAccessible(true);b.append(name).append("=").append(f.get(state)).append(";");}return b.toString();
 }
 @SuppressWarnings("unchecked") private static Map<UUID,Object> map(Class<?> type,String name)throws Exception{
  Field f=type.getDeclaredField(name);f.setAccessible(true);return (Map<UUID,Object>)f.get(null);
 }
 private static void check(boolean ok,String reason){if(!ok)throw new AssertionError(reason);}
}
'''
})
CASES=('awareness-first','weapon-first','client-player','no-target','los','terrain','rear','friendly','player','empty','no-session')


def sha(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for block in iter(lambda:f.read(1048576),b''):h.update(block)
 return h.hexdigest()


def inventory(paths):
 result={}
 for path in paths:
  files=sorted(f for f in path.rglob('*') if f.is_file()) if path.is_dir() else [path]
  for f in files:result[str(f)]=sha(f)
 return result


def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--java-home',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
 mode=p.add_mutually_exclusive_group(required=True);mode.add_argument('--source-root',type=Path);mode.add_argument('--classes',type=Path)
 p.add_argument('--source-provenance',type=Path);p.add_argument('--awareness-override',type=Path);p.add_argument('--weapon-override',type=Path)
 a=p.parse_args()
 if a.classes and (not a.source_provenance or a.awareness_override or a.weapon_override):p.error('build mode requires provenance and disallows source overrides')
 out=a.output.absolute();out.mkdir(mode=0o700,parents=False,exist_ok=False)
 source=(a.source_root or a.source_provenance).resolve()/'com/wwdebug/autopilot'
 originals=[(a.awareness_override or source/'CombatAwarenessManager.java').resolve(),(a.weapon_override or source/'CombatWeaponManager.java').resolve(),
            source/'MobPilotGate.java',source/'FlightPhase.java']
 java=(a.java_home/'bin/java').resolve();javac=(a.java_home/'bin/javac').resolve()
 classes=out/'classes';classes.mkdir();empty=out/'empty-sourcepath';empty.mkdir();sources=[]
 for name,data in STUBS.items():
  path=out/'fixture-source'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(data);sources.append(path)
 for original in originals:
  dest=out/'production-source'/original.name;dest.parent.mkdir(exist_ok=True);dest.write_bytes(original.read_bytes());sources.append(dest)
 inputs=originals+[Path(__file__).resolve(),WEAPON_TEST.resolve(),java,javac];built=a.classes.resolve() if a.classes else None
 observed=[built] if built else []
 before={'inputs':inventory(inputs),'classpath':inventory(observed),'snapshots':inventory(sources)};(out/'before.json').write_text(json.dumps(before,indent=2)+'\n')
 def run(name,argv):
  r=subprocess.run(argv,cwd=out,capture_output=True);(out/(name+'.json')).write_text(json.dumps({'argv':argv,'cwd':str(out),'exit':r.returncode},indent=2)+'\n')
  (out/(name+'.stdout')).write_bytes(r.stdout);(out/(name+'.stderr')).write_bytes(r.stderr);print(name,r.returncode,flush=True);return r.returncode
 failed=run('compile',[str(javac),'-proc:none','--release','17','-cp',str(classes),'-sourcepath',str(empty),'-d',str(classes),*map(str,sources)])!=0
 if not failed and built:
  for name in ('CombatAwarenessManager.class','CombatWeaponManager.class','CombatWeaponManager$State.class','MobPilotGate.class','FlightPhase.class','FlightPhase$1.class'):
   relative=Path('com/wwdebug/autopilot')/name;(classes/relative).write_bytes((built/relative).read_bytes())
 if not failed:
  for case in CASES:failed+=run(case,[str(java),'-Xmx128m','-Xverify:all','-Xlog:class+load=info:file='+str(out/(case+'.classes.log')),'-cp',str(classes),'com.wwdebug.autopilot.IntegrationProbe',case])!=0
 after={'inputs':inventory(inputs),'classpath':inventory(observed),'snapshots':inventory(sources),'classes':inventory([classes])}
 (out/'after.json').write_text(json.dumps(after,indent=2)+'\n')
 if before['inputs']!=after['inputs'] or before['classpath']!=after['classpath'] or before['snapshots']!=after['snapshots']:
  print('input changed during run',file=sys.stderr);failed+=1
 return 1 if failed else 0

if __name__=='__main__':sys.exit(main())
