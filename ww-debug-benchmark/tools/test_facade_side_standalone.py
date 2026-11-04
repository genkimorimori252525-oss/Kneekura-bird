#!/usr/bin/env python3
"""Exercise the real fighter facade with isolated stand-ins, without a game or world.

The fake scene and marker model shared static state; they do not prove actual Minecraft
client/server sharing, native Mixin dispatch, or safe server-side cleanup.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

STUBS = {
 'net/minecraft/world/level/Level.java': '''
package net.minecraft.world.level;
public class Level { public boolean isClientSide; public Level(boolean client){isClientSide=client;} }
''',
 'net/minecraft/server/level/ServerLevel.java': '''
package net.minecraft.server.level;
import net.minecraft.server.MinecraftServer;
import net.minecraft.world.level.Level;
public class ServerLevel extends Level { public ServerLevel(){super(false);} public MinecraftServer getServer(){return null;} }
''',
 'net/minecraft/world/entity/Entity.java': '''
package net.minecraft.world.entity;
import java.util.UUID;
import net.minecraft.world.level.Level;
public class Entity {
 public final UUID id=new UUID(0,42); public Level world; public boolean fighter;
 public Entity(Level level,boolean fighter){world=level;this.fighter=fighter;}
 public UUID getUUID(){return id;} public Level level(){return world;}
}
''',
 'com/wwdebug/autopilot/Tracker.java': '''
package com.wwdebug.autopilot;
import java.util.UUID;
public class Tracker {
 public static final UUID ID=new UUID(0,42);
 public static boolean scene=true,marker=true;
 public static int awarenessClear,weaponClear,defenseClear,offenseClear,awarenessTick,weaponTick;
 public static int registry,energyApply,energyActive,defenseApply,defenseActive,offenseApply;
 public static boolean fighter,energyClaim; public static String proposal="";
 public static int calls(){return awarenessClear+weaponClear+defenseClear+offenseClear+awarenessTick+weaponTick
  +registry+energyApply+energyActive+defenseApply+defenseActive+offenseApply;}
}
''',
 'com/wwdebug/autopilot/FlightProfile.java': '''
package com.wwdebug.autopilot;
public class FlightProfile { private final boolean fighter; FlightProfile(boolean f){fighter=f;} public boolean isFighter(){return fighter;} }
''',
 'com/wwdebug/autopilot/AutopilotProfileRegistry.java': '''
package com.wwdebug.autopilot;
import java.util.Optional; import net.minecraft.server.MinecraftServer; import net.minecraft.world.entity.Entity;
public class AutopilotProfileRegistry {
 public static Optional<FlightProfile> resolve(MinecraftServer server,Entity e){Tracker.registry++;return Optional.of(new FlightProfile(e.fighter));}
}
''',
 'com/wwdebug/autopilot/CombatAwarenessManager.java': '''
package com.wwdebug.autopilot;
import java.util.UUID; import net.minecraft.world.entity.Entity;
public class CombatAwarenessManager {
 public static void clear(UUID id){Tracker.awarenessClear++;if(id.equals(Tracker.ID)){Tracker.scene=false;Tracker.marker=false;}}
 public static void tick(Entity e){Tracker.awarenessTick++;}
}
''',
 'com/wwdebug/autopilot/CombatWeaponManager.java': '''
package com.wwdebug.autopilot;
import java.util.UUID; import net.minecraft.world.entity.Entity;
public class CombatWeaponManager { public static void clear(UUID id){Tracker.weaponClear++;} public static void tick(Entity e){Tracker.weaponTick++;} }
''',
 'com/wwdebug/autopilot/EnergyFighterApexYawAdapter.java': '''
package com.wwdebug.autopilot;
import java.util.Optional; import net.minecraft.world.entity.Entity;
public class EnergyFighterApexYawAdapter {
 public static Optional<ControlProposal> applyControl(Entity e){Tracker.energyApply++;return Tracker.proposal.equals("energy")?Optional.of(SideProbe.energy()):Optional.empty();}
 public static boolean active(Entity e){Tracker.energyActive++;return Tracker.energyClaim;}
}
''',
 'com/wwdebug/autopilot/DefensiveAirCombatManager.java': '''
package com.wwdebug.autopilot;
import java.util.*; import net.minecraft.world.entity.Entity;
public class DefensiveAirCombatManager {
 public static void clear(UUID id){Tracker.defenseClear++;}
 public static Optional<ControlProposal> applyControl(Entity e){Tracker.defenseApply++;return Tracker.proposal.equals("defense")?Optional.of(SideProbe.defense()):Optional.empty();}
 public static boolean active(Entity e){Tracker.defenseActive++;return false;}
}
''',
 'com/wwdebug/autopilot/AirCombatManeuverManager.java': '''
package com.wwdebug.autopilot;
import java.util.*; import net.minecraft.world.entity.Entity;
public class AirCombatManeuverManager {
 public static void clear(UUID id){Tracker.offenseClear++;}
 public static Optional<ControlProposal> applyControl(Entity e){Tracker.offenseApply++;return Tracker.proposal.equals("offense")?Optional.of(SideProbe.offense()):Optional.empty();}
}
''',
 'com/wwdebug/autopilot/SideProbe.java': '''
package com.wwdebug.autopilot;
import net.minecraft.world.level.Level; import net.minecraft.server.level.ServerLevel; import net.minecraft.world.entity.Entity;
import com.wwdebug.autopilot.ControlAuthorityArbiter.Authority;
public class SideProbe {
 public static ControlProposal energy(){return new ControlProposal(Authority.ENERGY_FIGHTER_REENGAGEMENT,0,0,0,0,"fixture");}
 public static ControlProposal defense(){return new ControlProposal(Authority.DEFENSIVE_COMBAT,0,0,0,0,"fixture");}
 public static ControlProposal offense(){return new ControlProposal(Authority.OFFENSIVE_COMBAT,0,0,0,0,"fixture");}
 public static void main(String[] args){
  String c=args[0];boolean client=c.startsWith("client-");boolean fighter=!c.contains("nonfighter");
  if(c.equals("server-risk-null")){
   ControlOutcome result=FighterCombatFacade.applyControl(null,true);
   check(result.authority()==Authority.NONE && Tracker.calls()==0,"collision suppression must retain null short-circuit");
   System.out.println("PASS "+c+" "+summary());return;
  }
  Entity aircraft=new Entity(client?new Level(true):new ServerLevel(),fighter);
  Entity fakeServerOwner=new Entity(new ServerLevel(),true);
  check(fakeServerOwner!=aircraft && fakeServerOwner.id.equals(aircraft.id) && fakeServerOwner.id.equals(Tracker.ID),
        "fixture requires separate server/client objects sharing the scene UUID");
  boolean control=c.endsWith("control") || c.equals("client-risk") || c.startsWith("server-proposal-") || c.equals("server-claimed") || c.equals("server-risk");
  if(c.startsWith("server-proposal-")) Tracker.proposal=c.substring("server-proposal-".length());
  if(c.equals("server-claimed")) Tracker.energyClaim=true;
  ControlOutcome outcome=null;
  if(c.equals("direct-clear")){FighterCombatFacade.clear(aircraft.id);}
  else if(control){outcome=FighterCombatFacade.applyControl(aircraft,c.endsWith("risk"));}
  else FighterCombatFacade.tick(aircraft);
  if(client){
   check(Tracker.calls()==0 && Tracker.scene && Tracker.marker,"CONTRACT_FAIL client called other manager or cleared shared fixture scene/marker: "+summary());
   if(control)check(outcome.authority()==Authority.NONE && !outcome.claimed(),"client must return no control");
  } else if(c.startsWith("server-nonfighter") || c.equals("direct-clear")){
   check(Tracker.awarenessClear==1 && Tracker.weaponClear==1 && Tracker.defenseClear==1 && Tracker.offenseClear==1
     && !Tracker.scene && !Tracker.marker,"server nonfighter/direct clear changed "+summary());
  } else if(c.equals("server-fighter-tick")){
   check(Tracker.registry==1 && Tracker.awarenessTick==1 && Tracker.weaponTick==1 && Tracker.calls()==3 && Tracker.scene && Tracker.marker,"fighter tick changed "+summary());
  } else if(c.equals("server-risk")){
   check(Tracker.calls()==0 && outcome.authority()==Authority.NONE,"collision risk priority changed "+summary());
  } else if(c.equals("server-proposal-energy")){
   check(Tracker.registry==1 && Tracker.energyApply==1 && Tracker.energyActive==0 && Tracker.defenseApply==0 && outcome.authority()==Authority.ENERGY_FIGHTER_REENGAGEMENT && outcome.pendingWrite().isPresent(),"energy priority changed "+summary());
  } else if(c.equals("server-proposal-defense")){
   check(Tracker.registry==1 && Tracker.energyApply==1 && Tracker.energyActive==1 && Tracker.defenseApply==1 && Tracker.defenseActive==0 && Tracker.offenseApply==0 && outcome.authority()==Authority.DEFENSIVE_COMBAT && outcome.pendingWrite().isPresent(),"defense priority changed "+summary());
  } else if(c.equals("server-proposal-offense")){
   check(Tracker.registry==1 && Tracker.energyApply==1 && Tracker.energyActive==1 && Tracker.defenseApply==1 && Tracker.defenseActive==1 && Tracker.offenseApply==1 && outcome.authority()==Authority.OFFENSIVE_COMBAT && outcome.pendingWrite().isPresent(),"offense priority changed "+summary());
  } else if(c.equals("server-claimed")){
   check(Tracker.registry==1 && Tracker.energyApply==1 && Tracker.energyActive==1 && Tracker.defenseApply==0 && outcome.authority()==Authority.ENERGY_FIGHTER_REENGAGEMENT && outcome.pendingWrite().isEmpty(),"claim priority changed "+summary());
  } else throw new AssertionError("unknown case "+c);
  System.out.println("PASS "+c+" "+summary());
 }
 private static String summary(){return "calls="+Tracker.calls()+" clear="+Tracker.awarenessClear+"/"+Tracker.weaponClear+"/"+Tracker.defenseClear+"/"+Tracker.offenseClear+" scene="+Tracker.scene+" marker="+Tracker.marker;}
 private static void check(boolean ok,String message){if(!ok)throw new AssertionError(message);}
}
'''
}
CASES=('client-tick','client-control','client-risk','server-nonfighter-tick','server-nonfighter-control',
       'server-fighter-tick','server-risk','server-proposal-energy','server-proposal-defense',
       'server-proposal-offense','server-claimed','direct-clear','server-risk-null')


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
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--java-home',type=Path,required=True)
 p.add_argument('--dependencies-json',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
 g=p.add_mutually_exclusive_group(required=True);g.add_argument('--source-root',type=Path);g.add_argument('--classes',type=Path)
 p.add_argument('--source-provenance',type=Path);a=p.parse_args()
 if a.classes and not a.source_provenance:p.error('--classes requires --source-provenance')
 out=a.output.absolute();out.mkdir(mode=0o700,parents=False,exist_ok=False)
 src=(a.source_root or a.source_provenance).resolve();actual=[src/'com/wwdebug/autopilot/FighterCombatFacade.java']
 deps=[Path(x).resolve() for x in json.loads(a.dependencies_json.read_text())]
 java=(a.java_home/'bin/java').resolve();javac=(a.java_home/'bin/javac').resolve()
 fake=out/'fixture-classes';fake.mkdir();empty=out/'empty-sourcepath';empty.mkdir()
 production=a.classes.resolve() if a.classes else out/'production'
 if not a.classes:production.mkdir()
 fake_sources=[]
 for name,content in STUBS.items():
  path=out/'fixture-source'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(content);fake_sources.append(path)
 observed=deps+([production] if a.classes else []);inputs=actual+fake_sources+[Path(__file__).resolve(),a.dependencies_json.resolve(),java,javac]
 before={'inputs':inventory(inputs),'classpath':inventory(observed)};(out/'before.json').write_text(json.dumps(before,indent=2)+'\n')
 def run(name,argv):
  r=subprocess.run(argv,cwd=out,capture_output=True);(out/(name+'.json')).write_text(json.dumps({'argv':argv,'cwd':str(out),'exit':r.returncode},indent=2)+'\n')
  (out/(name+'.stdout')).write_bytes(r.stdout);(out/(name+'.stderr')).write_bytes(r.stderr);print(name,r.returncode,flush=True);return r.returncode
 deps_cp=os.pathsep.join(map(str,deps));failed=0
 if not a.classes:failed+=run('compile-production',[str(javac),'-proc:none','--release','17','-cp',deps_cp,'-sourcepath',str(empty),'-d',str(production),*map(str,actual)])!=0
 cp=str(production)+os.pathsep+deps_cp
 if not failed:failed+=run('compile-fixture',[str(javac),'-proc:none','--release','17','-cp',cp,'-sourcepath',str(empty),'-d',str(fake),*map(str,fake_sources)])!=0
 if not failed:
  cp=str(fake)+os.pathsep+cp
  for case in CASES:failed+=run(case,[str(java),'-Xmx128m','-Xverify:all','-Xlog:class+load=info:file='+str(out/(case+'.classes.log')),'-cp',cp,'com.wwdebug.autopilot.SideProbe',case])!=0
 after={'inputs':inventory(inputs),'classpath':inventory(observed),'fixture_classes':inventory([fake]),'production_classes':inventory([production])}
 (out/'after.json').write_text(json.dumps(after,indent=2)+'\n')
 if before['inputs']!=after['inputs'] or before['classpath']!=after['classpath']:print('input changed during run',file=sys.stderr);failed+=1
 return 1 if failed else 0

if __name__=='__main__':sys.exit(main())
