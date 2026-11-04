#!/usr/bin/env python3
"""Compare two synthetic write sequences using real ReflectiveAircraft source.

The policies are fixture code, not the game's arbiter. This does not run Minecraft,
exercise safety gates, establish the right policy, or recommend repeated writes.
"""
import argparse
import hashlib
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'src/main/java/com/wwdebug/benchmark/ReflectiveAircraft.java'

# The four minimal stand-ins are from the #203/#206 setter fixture. Their
# presence only satisfies the actual adapter's compile-time references.
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
}

# Each pair is (first action, second action) for the named setter. The first
# action is shared by all policies. "after" mutates then throws; "noop" returns.
MATRIX = {
    'both-ok': (('write', 'write'), ('write', 'write')),
    'input-before': (('before', 'write'), ('write', 'write')),
    'engine-before': (('write', 'write'), ('before', 'write')),
    'input-after': (('after', 'write'), ('write', 'write')),
    'engine-after': (('write', 'write'), ('after', 'write')),
    'input-second': (('write', 'before'), ('write', 'write')),
    'engine-second': (('write', 'write'), ('write', 'before')),
    'noop': (('noop', 'noop'), ('noop', 'noop')),
}
POLICIES = ('baseline', 'replacement')
PROBE = r'''package fixture;
import com.wwdebug.benchmark.ReflectiveAircraft;
import net.minecraft.world.entity.Entity;
import java.util.*;
public class Probe {
  static class Plane extends Entity {
    final String scenario; final List<String> events=new ArrayList<>();
    int inputs, engines, inputMutations, engineMutations;
    float x=-9,y=-9,z=-9,engine=-9;
    Plane(String scenario){this.scenario=scenario;}
    public void setInputs(float a,float b,float c){
      int n=++inputs; events.add("input"+n+":enter:"+a+","+b+","+c);
      if (((scenario.equals("input-before")||scenario.equals("both-before"))&&n==1)
          || (scenario.equals("input-second")&&n==2)) {
        events.add("input"+n+":throw-before"); throw new IllegalStateException("synthetic");
      }
      if (scenario.equals("noop")) events.add("input"+n+":noop");
      else {x=a;y=b;z=c;inputMutations++;events.add("input"+n+":mutate");}
      if (scenario.equals("input-after")&&n==1){events.add("input"+n+":throw-after");throw new IllegalStateException("synthetic");}
      events.add("input"+n+":return");
    }
    public void setEngineTarget(float a){
      int n=++engines; events.add("engine"+n+":enter:"+a);
      if (((scenario.equals("engine-before")||scenario.equals("both-before"))&&n==1)
          || (scenario.equals("engine-second")&&n==2)) {
        events.add("engine"+n+":throw-before"); throw new IllegalStateException("synthetic");
      }
      if (scenario.equals("noop")) events.add("engine"+n+":noop");
      else {engine=a;engineMutations++;events.add("engine"+n+":mutate");}
      if (scenario.equals("engine-after")&&n==1){events.add("engine"+n+":throw-after");throw new IllegalStateException("synthetic");}
      events.add("engine"+n+":return");
    }
    void snapshot(String label){
      System.out.println(label+"="+x+","+y+","+z+","+engine+","+inputs+","+engines+","+inputMutations+","+engineMutations);
      System.out.println(label+"_events="+String.join(";",events));
    }
  }
  public static void main(String[] args){
    Plane p=new Plane(args[0]); String policy=args[1];
    if(!ReflectiveAircraft.isControllable(p))throw new AssertionError("setter methods missing");
    p.snapshot("initial");
    ReflectiveAircraft.applyControl(p,-0.35099998f,0f,-0.15f,1f);
    p.snapshot("first");
    switch(policy){
      case "baseline" -> ReflectiveAircraft.applyControl(p,0.0012139524f,0f,-2.341649E-4f,0.08f);
      case "replacement" -> ReflectiveAircraft.applyControl(p,-0.35099998f,0f,-0.15f,1f);
      default -> throw new AssertionError("unknown policy");
    }
    p.snapshot("final");
  }
}
'''

def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def expected(case, policy):
    """Independent matrix oracle: full argument, order, state and side effects."""
    input_actions, engine_actions = MATRIX[case]
    state = ['-9.0', '-9.0', '-9.0', '-9.0']
    counts = [0, 0, 0, 0]
    events = []
    snapshots = {}
    def snap(label):
        snapshots[label] = ','.join(state + list(map(str, counts)))
        snapshots[label+'_events'] = ';'.join(events)
    snap('initial')
    for n in range(2):
        vector = (['0.0012139524', '0.0', '-2.341649E-4', '0.08'] if n == 1 and policy == 'baseline'
                  else ['-0.35099998', '0.0', '-0.15', '1.0'])
        for field, actions, count_index, mutation_index, indices in (
            ('input', input_actions, 0, 2, (0, 1, 2)),
            ('engine', engine_actions, 1, 3, (3,)),
        ):
            counts[count_index] += 1
            prefix = field+str(n+1)
            events.append(prefix+':enter:'+','.join(vector[i] for i in indices))
            action = actions[n]
            if action == 'before':
                events.append(prefix+':throw-before')
                continue
            if action == 'noop':
                events.append(prefix+':noop')
            else:
                for i in indices:
                    state[i] = vector[i]
                counts[mutation_index] += 1
                events.append(prefix+':mutate')
            if action == 'after':
                events.append(prefix+':throw-after')
            else:
                events.append(prefix+':return')
        if n == 0:
            snap('first')
    snap('final')
    return snapshots

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--java-home', type=pathlib.Path, required=True)
    parser.add_argument('--output', type=pathlib.Path, required=True)
    args=parser.parse_args()
    sys.dont_write_bytecode=True
    stubs=dict(STUBS)
    stubs['fixture/Probe.java']=PROBE
    parent=args.output.absolute().parent.resolve(strict=True)
    checkout=ROOT.parent
    if parent==checkout or checkout in parent.parents:
        parser.error('output must be outside the checkout')
    out=parent/args.output.name
    out.mkdir(mode=0o700)
    src,classes,empty=out/'stubs',out/'classes',out/'empty'
    for d in (src,classes,empty): d.mkdir()
    paths=[]
    for name,body in stubs.items():
        p=src/name; p.parent.mkdir(parents=True,exist_ok=True); p.write_text(body); paths.append(p)
    java=args.java_home.resolve()/'bin/java'; javac=args.java_home.resolve()/'bin/javac'
    inputs=[SOURCE,pathlib.Path(__file__).resolve(),java,javac,*paths]
    before={str(p):digest(p) for p in inputs}
    (out/'runner-snapshot.py').write_bytes(pathlib.Path(__file__).read_bytes())
    report={'scope':'Synthetic call-sequence models only; not real arbiter, terrain, collision, '
            'combat, player, stale state, MOD or aircraft physics. Not a policy recommendation.',
            'inputs_before':before,'runs':{},'comparisons':{}}
    def run(name,argv):
        p=subprocess.run(argv,cwd=out,capture_output=True,text=True,timeout=30)
        (out/(name+'.stdout')).write_text(p.stdout); (out/(name+'.stderr')).write_text(p.stderr)
        report['runs'][name]={'argv':argv,'exit':p.returncode}
        print(name,p.returncode,flush=True)
        return p
    compile=run('compile',[str(javac),'-encoding','UTF-8','-proc:none','--release','17','-classpath',str(empty),
        '-sourcepath',str(empty),'-d',str(classes),str(SOURCE),*map(str,paths)])
    if compile.returncode==0:
        for case in MATRIX:
            for policy in POLICIES:
                name=case+'--'+policy
                result=run(name,[str(java),'-Xmx64m','-Xverify:all',
                    '-Xlog:class+load=info:file='+str(out/(name+'.classes.log')),
                    '-cp',str(classes),'fixture.Probe',case,policy])
                observed={}
                errors=[]
                for line in result.stdout.splitlines():
                    key,sep,value=line.partition('=')
                    if not sep or key in observed: errors.append('invalid/duplicate output: '+line)
                    else: observed[key]=value
                want=expected(case,policy)
                if observed!=want: errors.append('snapshot/event mismatch')
                report['comparisons'][name]={'expected':want,'observed':observed,'errors':errors}
    report['inputs_after']={str(p):digest(p) for p in inputs}
    report['inputs_unchanged']=before==report['inputs_after']
    report['runner_snapshot_sha256']=digest(out/'runner-snapshot.py')
    report['compiled_classes']={str(p):digest(p) for p in sorted(classes.rglob('*.class'))}
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    return 0 if (report['inputs_unchanged'] and len(report['runs'])==1+len(MATRIX)*len(POLICIES)
        and all(r['exit']==0 for r in report['runs'].values())
        and len(report['comparisons'])==len(MATRIX)*len(POLICIES)
        and all(not r['errors'] for r in report['comparisons'].values())) else 1

if __name__=='__main__':
    sys.exit(main())
