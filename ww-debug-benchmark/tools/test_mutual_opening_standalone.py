#!/usr/bin/env python3
"""Direct-call fixture for the real mutual-opening adapter; not a game or world.

A supplied classpath is used for mapped Vec3/AABB/Component. Entity, server, reflective
writes, profile and logging are deterministic stand-ins; no native setters are invoked.
Each case uses a separate JVM and a deliberately ordered synthetic candidate list.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

STUBS = {
    'net/minecraft/world/entity/Entity.java': '''
package net.minecraft.world.entity;
import java.util.*;
import net.minecraft.network.chat.Component;
import net.minecraft.world.phys.AABB;
import net.minecraft.world.phys.Vec3;
public class Entity {
 private static long nextId;
 public final UUID id = new UUID(0, ++nextId);
 public String name = "AUTOPILOT TEST PRIMARY";
 public Set<String> tags = new HashSet<>();
 public LivingEntity pilot;
 public boolean removed, airplane = true;
 public int moves, velocities, rolls, warms, controls;
 public Vec3 position = new Vec3(0, 0, 0), velocity = new Vec3(0, 0, 1);
 public UUID getUUID(){return id;}
 public Component getName(){return Component.literal(name);}
 public Set<String> getTags(){return tags;}
 public LivingEntity getControllingPassenger(){return pilot;}
 public boolean isRemoved(){return removed;}
 public AABB getBoundingBox(){return new AABB(0,0,0,1,1,1);}
 public Vec3 getLookAngle(){return new Vec3(0,0,1);}
 public Vec3 getDeltaMovement(){return velocity;}
 public Vec3 position(){return position;}
 public void moveTo(double x,double y,double z,float yaw,float pitch){moves++; position=new Vec3(x,y,z);}
 public void setDeltaMovement(Vec3 v){velocities++;velocity=v;}
 public float distanceTo(Entity other){return (float) position.distanceTo(other.position);}
}
''',
    'net/minecraft/world/entity/LivingEntity.java': 'package net.minecraft.world.entity; public class LivingEntity extends Entity {}',
    'net/minecraft/world/entity/Mob.java': 'package net.minecraft.world.entity; public class Mob extends LivingEntity {}',
    'net/minecraft/world/entity/player/Player.java': 'package net.minecraft.world.entity.player; public class Player extends net.minecraft.world.entity.LivingEntity {}',
    'net/minecraft/server/level/ServerLevel.java': '''
package net.minecraft.server.level;
import java.util.*;
import java.util.function.Predicate;
import net.minecraft.server.MinecraftServer;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.phys.AABB;
public class ServerLevel {
 public final List<Entity> candidates = new ArrayList<>();
 public List<Entity> getEntities(Entity except, AABB box, Predicate<? super Entity> filter) {
   return candidates.stream().filter(e -> e != except).filter(filter).toList();
 }
 public MinecraftServer getServer(){return null;}
}
''',
    'com/wwdebug/benchmark/ReflectiveAircraft.java': '''
package com.wwdebug.benchmark;
import net.minecraft.world.entity.Entity;
public class ReflectiveAircraft {
 public static boolean isAirplane(Entity e){return e.airplane;}
 public static void setRoll(Entity e,float roll){e.rolls++;}
 public static void warmEngine(Entity e,float target){e.warms++;}
 public static void applyControl(Entity e,float x,float y,float z,float engine){e.controls++;}
}
''',
    'com/wwdebug/autopilot/AutopilotProfileRegistry.java': '''
package com.wwdebug.autopilot;
import java.util.Optional;
import net.minecraft.server.MinecraftServer;
import net.minecraft.world.entity.Entity;
public class AutopilotProfileRegistry {
 public static Optional<FlightProfile> resolve(MinecraftServer server, Entity e){return Optional.empty();}
}
''',
    'com/wwdebug/autopilot/FlightProfile.java': 'package com.wwdebug.autopilot; public class FlightProfile { public double cruiseSpeedBps(){return 34.0;} }',
    'com/wwdebug/autopilot/AutopilotLogManager.java': '''
package com.wwdebug.autopilot;
import net.minecraft.server.MinecraftServer;
import net.minecraft.world.entity.Entity;
public class AutopilotLogManager {
 public static int events;
 public static void writeEvent(MinecraftServer server, Entity e,String type,String detail,FlightPhase phase){events++;}
}
''',
    'com/wwdebug/autopilot/OpeningProbe.java': '''
package com.wwdebug.autopilot;
import java.lang.reflect.Field;
import java.util.Set;
import java.util.UUID;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.Mob;
import net.minecraft.world.entity.player.Player;
public class OpeningProbe {
 private static final String TAG="wwcombat:mutual_opponent";
 public static void main(String[] args) throws Exception {
  String c=args[0]; System.setProperty("wwdebug.flightGameTestScenario", "dogfight_mutual");
  ServerLevel level=new ServerLevel(); Entity primary=new Entity(); primary.pilot=new Mob();
  Entity first=new Entity(); first.tags.add(TAG); first.pilot=new Mob();
  Entity second=new Entity(); second.tags.add(TAG); second.pilot=new Mob();
  if(c.contains("player")) first.pilot=new Player();
  if(c.contains("empty")) first.pilot=null;
  if(c.equals("wrong-scenario")) System.setProperty("wwdebug.flightGameTestScenario", "full");
  if(c.equals("wrong-name")) primary.name="ordinary";
  if(c.equals("tagged-primary")) primary.tags.add(TAG);
  if(c.equals("removed-first")) first.removed=true;
  if(c.equals("nonairplane-first")) first.airplane=false;
  if(!c.equals("no-candidate")) level.candidates.add(first);
  if(c.endsWith("-first") || c.equals("removed-first") || c.equals("nonairplane-first")) level.candidates.add(second);
  MutualDogfightOpeningAdapter.apply(level,primary,FlightPhase.CRUISE_OUTBOUND);
  boolean refused = c.equals("player") || c.equals("empty") || c.equals("player-first") || c.equals("empty-first") || c.equals("retry-player") || c.equals("retry-empty");
  boolean noAction=refused || c.equals("wrong-scenario") || c.equals("wrong-name") || c.equals("tagged-primary") || c.equals("no-candidate");
  if(noAction) {
   check(writes(first)==0 && writes(second)==0,"CONTRACT_FAIL unexpected mutation first="+describe(first)+" second="+describe(second));
   check(!applied(primary.id) && AutopilotLogManager.events==0,"refusal must not mark APPLIED or log success");
  } else {
   Entity expected=(c.equals("removed-first") || c.equals("nonairplane-first")) ? second : first;
   Entity other=expected==first?second:first;
   check(expected.moves==1 && expected.velocities==1 && expected.rolls==1 && expected.warms==1 && expected.controls==1,
      "mob positive expected one of each operation "+describe(expected));
   check(writes(other)==0 && applied(primary.id) && AutopilotLogManager.events==1,"wrong selection or missing success state");
   MutualDogfightOpeningAdapter.apply(level,primary,FlightPhase.CRUISE_OUTBOUND);
   check(expected.moves==1 && expected.velocities==1 && expected.rolls==1 && expected.warms==1 && expected.controls==1 && AutopilotLogManager.events==1,"duplicate opening");
  }
  if(c.startsWith("retry-")) {
   first.pilot=new Mob();
   MutualDogfightOpeningAdapter.apply(level,primary,FlightPhase.CRUISE_OUTBOUND);
   check(first.moves==1 && first.velocities==1 && first.rolls==1 && first.warms==1 && first.controls==1 && applied(primary.id) && AutopilotLogManager.events==1,"same opponent mob retry failed");
  }
  System.out.println("PASS "+c+" first="+describe(first)+" second="+describe(second)+" applied="+applied(primary.id)+" events="+AutopilotLogManager.events);
 }
 private static int writes(Entity e){return e.moves+e.velocities+e.rolls+e.warms+e.controls;}
 private static String describe(Entity e){return e.moves+"/"+e.velocities+"/"+e.rolls+"/"+e.warms+"/"+e.controls;}
 @SuppressWarnings("unchecked") private static boolean applied(UUID id)throws Exception{
  Field field=MutualDogfightOpeningAdapter.class.getDeclaredField("APPLIED");field.setAccessible(true);return ((Set<UUID>)field.get(null)).contains(id);
 }
 private static void check(boolean ok,String reason){if(!ok)throw new AssertionError(reason);}
}
'''
}
CASES = ('player','empty','player-first','empty-first','retry-player','retry-empty','mob',
         'wrong-scenario','wrong-name','tagged-primary','no-candidate','removed-first','nonairplane-first','mob-first')


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1048576),b''): h.update(block)
    return h.hexdigest()


def inventory(paths):
    result={}
    for path in paths:
        files=sorted(f for f in path.rglob('*') if f.is_file()) if path.is_dir() else [path]
        for f in files: result[str(f)]=sha(f)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--java-home',type=Path,required=True)
    p.add_argument('--dependencies-json',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    g=p.add_mutually_exclusive_group(required=True)
    g.add_argument('--source-root',type=Path)
    g.add_argument('--classes',type=Path)
    p.add_argument('--source-provenance',type=Path)
    a=p.parse_args()
    if a.classes and not a.source_provenance: p.error('--classes requires --source-provenance')
    out=a.output.absolute();out.mkdir(mode=0o700,parents=False,exist_ok=False)
    src=(a.source_root or a.source_provenance).resolve()
    actual=[src/'com/wwdebug/autopilot'/name for name in ('MutualDogfightOpeningAdapter.java','MobPilotGate.java')]
    deps=[Path(x).resolve() for x in json.loads(a.dependencies_json.read_text())]
    java=(a.java_home/'bin/java').resolve();javac=(a.java_home/'bin/javac').resolve()
    output=out/'fixture-classes';output.mkdir();empty=out/'empty-sourcepath';empty.mkdir()
    fake_sources=[]
    for name,content in STUBS.items():
        path=out/'fixture-source'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(content);fake_sources.append(path)
    observed=deps+([a.classes.resolve()] if a.classes else [])
    inputfiles=actual+fake_sources+[Path(__file__).resolve(),a.dependencies_json.resolve(),java,javac]
    before={'inputs':inventory(inputfiles),'classpath':inventory(observed)}
    (out/'before.json').write_text(json.dumps(before,indent=2)+'\n')
    def run(name,argv):
        r=subprocess.run(argv,cwd=out,capture_output=True)
        (out/(name+'.json')).write_text(json.dumps({'argv':argv,'cwd':str(out),'exit':r.returncode},indent=2)+'\n')
        (out/(name+'.stdout')).write_bytes(r.stdout);(out/(name+'.stderr')).write_bytes(r.stderr)
        print(name,r.returncode,flush=True);return r.returncode
    cp=os.pathsep.join(map(str,([a.classes.resolve()] if a.classes else [])+deps))
    compile_sources=fake_sources+([] if a.classes else actual)
    failed=run('compile',[str(javac),'-proc:none','--release','17','-cp',cp,'-sourcepath',str(empty),'-d',str(output),*map(str,compile_sources)]) != 0
    if not failed:
        cp=str(output)+os.pathsep+cp
        for case in CASES:
            failed+=run(case,[str(java),'-Xmx128m','-Xverify:all','-Xlog:class+load=info:file='+str(out/(case+'.classes.log')),'-cp',cp,'com.wwdebug.autopilot.OpeningProbe',case]) != 0
    after={'inputs':inventory(inputfiles),'classpath':inventory(observed),'fixture_classes':inventory([output])}
    (out/'after.json').write_text(json.dumps(after,indent=2)+'\n')
    if before['inputs']!=after['inputs'] or before['classpath']!=after['classpath']:
        print('input changed during run',file=sys.stderr);failed+=1
    return 1 if failed else 0

if __name__=='__main__':sys.exit(main())
