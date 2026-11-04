#!/usr/bin/env python3
"""Observe real ReflectiveAircraft with synthetic setters; not a Minecraft test.

Two identical calls are observations, not a retry recommendation. Output directory must
not exist. No world, Forge runtime, aircraft physics, or Gradle is started.
"""
import argparse
import hashlib
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'src/main/java/com/wwdebug/benchmark/ReflectiveAircraft.java'
STUBS = {
    'net/minecraft/world/entity/Entity.java': '''package net.minecraft.world.entity;
import java.util.List; public class Entity { public List<Entity> getPassengers(){return List.of();} }
''',
    'net/minecraft/world/Container.java': '''package net.minecraft.world;
import net.minecraft.world.item.ItemStack; public interface Container { void setItem(int i, ItemStack s); }
''',
    'net/minecraft/world/item/ItemStack.java': '''package net.minecraft.world.item;
public class ItemStack { public ItemStack(Object item,int count){} }
''',
    'net/minecraft/world/item/Items.java': '''package net.minecraft.world.item;
public class Items { public static final Object COAL=new Object(); }
''',
    'fixture/Probe.java': '''package fixture;
import com.wwdebug.benchmark.ReflectiveAircraft;
import net.minecraft.world.entity.Entity;
import java.util.*;
public class Probe {
  static final class Plane extends Entity {
    final String scenario; final List<String> events=new ArrayList<>();
    int inputCalls, engineCalls, inputMutations, engineMutations;
    float x=-9,y=-9,z=-9,engine=-9;
    Plane(String scenario){this.scenario=scenario;}
    public void setInputs(float a,float b,float c) {
      int n=++inputCalls; events.add("inputs:"+n+":enter");
      if ((scenario.equals("input-before") || scenario.equals("both-before")) && n==1
          || scenario.equals("input-second") && n==2) {
        events.add("inputs:"+n+":throw-before"); throw new IllegalStateException("synthetic");
      }
      if (!scenario.equals("noop")) {x=a;y=b;z=c;inputMutations++;}
      events.add("inputs:"+n+":"+(scenario.equals("noop")?"noop":"mutated"));
      if (scenario.equals("input-after") && n==1) {
        events.add("inputs:"+n+":throw-after"); throw new IllegalStateException("synthetic");
      }
      events.add("inputs:"+n+":return");
    }
    public void setEngineTarget(float v) {
      int n=++engineCalls; events.add("engine:"+n+":enter");
      if ((scenario.equals("engine-before") || scenario.equals("both-before")) && n==1
          || scenario.equals("engine-second") && n==2) {
        events.add("engine:"+n+":throw-before"); throw new IllegalStateException("synthetic");
      }
      if (!scenario.equals("noop")) {engine=v;engineMutations++;}
      events.add("engine:"+n+":"+(scenario.equals("noop")?"noop":"mutated"));
      if (scenario.equals("engine-after") && n==1) {
        events.add("engine:"+n+":throw-after"); throw new IllegalStateException("synthetic");
      }
      events.add("engine:"+n+":return");
    }
    String state(){return "x="+x+",y="+y+",z="+z+",engine="+engine+",input_calls="+inputCalls+
      ",engine_calls="+engineCalls+",input_mutations="+inputMutations+",engine_mutations="+engineMutations;}
  }
  static void require(boolean b,String message){if(!b)throw new AssertionError(message);}
  public static void main(String[] args) {
    String c=args[0]; Plane p=new Plane(c);
    require(ReflectiveAircraft.isControllable(p),"methods not found");
    System.out.println("scenario="+c+" initial="+p.state());
    ReflectiveAircraft.applyControl(p,1,2,3,0.7f);
    System.out.println("after_first="+p.state()+" events="+p.events);
    require(p.inputCalls==1 && p.engineCalls==1,"both methods attempted after first call");
    boolean inputFirstFail=c.equals("input-before")||c.equals("both-before");
    boolean engineFirstFail=c.equals("engine-before")||c.equals("both-before");
    boolean noop=c.equals("noop");
    require(p.x==(inputFirstFail||noop?-9:1),"first input state");
    require(p.engine==(engineFirstFail||noop?-9:0.7f),"first engine state");
    require(p.inputMutations==(inputFirstFail||noop?0:1),"first input mutations");
    require(p.engineMutations==(engineFirstFail||noop?0:1),"first engine mutations");
    ReflectiveAircraft.applyControl(p,1,2,3,0.7f);
    System.out.println("after_second="+p.state()+" events="+p.events);
    require(p.inputCalls==2 && p.engineCalls==2,"both methods attempted after second call");
    require(p.x==(noop?-9:1) && p.y==(noop?-9:2) && p.z==(noop?-9:3),"second input state");
    require(p.engine==(noop?-9:0.7f),"second engine state");
    int expectedInputs=noop?0:2-(inputFirstFail?1:0)-(c.equals("input-second")?1:0);
    int expectedEngine=noop?0:2-(engineFirstFail?1:0)-(c.equals("engine-second")?1:0);
    require(p.inputMutations==expectedInputs && p.engineMutations==expectedEngine,"mutation counts");
    int i1=p.events.indexOf("inputs:1:enter"),e1=p.events.indexOf("engine:1:enter");
    int i2=p.events.indexOf("inputs:2:enter"),e2=p.events.indexOf("engine:2:enter");
    require(i1==0 && i1<e1 && e1<i2 && i2<e2,"setter order");
    System.out.println("classification=SYNTHETIC_OBSERVATION_PASSED");
  }
}
'''
}
CASES = ('both-ok', 'input-before', 'engine-before', 'both-before', 'input-after',
         'engine-after', 'input-second', 'engine-second', 'noop')

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--java-home', type=pathlib.Path, required=True)
    parser.add_argument('--output', type=pathlib.Path, required=True)
    args = parser.parse_args()
    out = args.output.absolute()
    out.mkdir(mode=0o700)
    sources, classes, empty = out/'stubs', out/'classes', out/'empty'
    for directory in (sources, classes, empty):
        directory.mkdir()
    fake_paths = []
    for name, contents in STUBS.items():
        path = sources/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents)
        fake_paths.append(path)
    java = args.java_home.resolve()/'bin/java'
    javac = args.java_home.resolve()/'bin/javac'
    inputs = [SOURCE, pathlib.Path(__file__).resolve(), java, javac, *fake_paths]
    before = {str(p): digest(p) for p in inputs}
    (out/'runner-snapshot.py').write_bytes(pathlib.Path(__file__).read_bytes())
    report = {'scope': 'Synthetic setter observation; no actual mod, server, world or physics. '
              'Two calls do not establish retry safety or real failure rates.',
              'inputs_before': before, 'runs': {}}
    def run(name, command):
        result = subprocess.run(command, cwd=out, capture_output=True, text=True, timeout=30)
        (out/(name+'.stdout')).write_text(result.stdout)
        (out/(name+'.stderr')).write_text(result.stderr)
        report['runs'][name] = {'argv': command, 'exit': result.returncode}
        print(name, result.returncode, flush=True)
        return result.returncode
    rc = run('compile', [str(javac), '-proc:none', '--release', '17', '-classpath', str(empty),
                         '-sourcepath', str(empty), '-d', str(classes), str(SOURCE),
                         *map(str, fake_paths)])
    if rc == 0:
        for case in CASES:
            run(case, [str(java), '-Xmx64m', '-Xverify:all',
                       '-Xlog:class+load=info:file='+str(out/(case+'.classes.log')),
                       '-cp', str(classes), 'fixture.Probe', case])
    report['inputs_after'] = {str(p): digest(p) for p in inputs}
    report['inputs_unchanged'] = report['inputs_before'] == report['inputs_after']
    report['runner_snapshot_sha256'] = digest(out/'runner-snapshot.py')
    report['compiled_classes'] = {str(p): digest(p) for p in sorted(classes.rglob('*.class'))}
    (out/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    return 0 if report['inputs_unchanged'] and len(report['runs'])==len(CASES)+1 and all(
        r['exit']==0 for r in report['runs'].values()) else 1

if __name__ == '__main__':
    sys.exit(main())
