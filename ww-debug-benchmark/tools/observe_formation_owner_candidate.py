#!/usr/bin/env python3
"""Private source-copy experiment; no Minecraft world or production source is modified."""
import argparse, difflib, hashlib, json, os, pathlib, shutil, subprocess, sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent / 'src/main/java'
BASE = HERE / 'inspect_pilot_identity.py'

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def once(value, old, new):
    if value.count(old) != 1:
        raise ValueError('expected exactly one transformation anchor: ' + old[:80])
    return value.replace(old, new, 1)

def transform_formation(text):
    text = once(text, 'import net.minecraft.world.entity.Entity;\n',
                'import net.minecraft.world.entity.Entity;\nimport net.minecraft.world.entity.Mob;\n')
    text = once(text, '    public static ControlOutcome applyControl(Entity aircraft) {\n', '''    public static ControlOutcome applyControl(Entity aircraft) {
        return evaluateWithPilot(aircraft).outcome();
    }

    record FormationEvaluation(ControlOutcome outcome, Mob pilot, ServerLevel level) { }

    static FormationEvaluation evaluateWithPilot(Entity aircraft) {
''')
    start = text.index('    static FormationEvaluation evaluateWithPilot(')
    end = text.index('    private static void applyCollisionAvoidance(', start)
    head, body, tail = text[:start], text[start:end], text[end:]
    body = once(body, '        if (!MobPilotGate.isMobPiloted(aircraft) || status.isEmpty()) {',
                '        Optional<Mob> pilot = MobPilotGate.pilotOf(aircraft);\n        if (pilot.isEmpty() || status.isEmpty()) {')
    body = body.replace('return ControlOutcome.none();', 'return new FormationEvaluation(ControlOutcome.none(), null, null);')
    body = once(body, '''return ControlOutcome.alreadyWrote(
                    ControlAuthorityArbiter.Authority.COLLISION_AVOIDANCE);''', '''return new FormationEvaluation(ControlOutcome.alreadyWrote(
                    ControlAuthorityArbiter.Authority.COLLISION_AVOIDANCE), null, null);''')
    body = once(body, '''return ControlOutcome.proposed(
                applyFormationSlot(level, aircraft, phase, snapshot, profile, leader, members));''', '''return new FormationEvaluation(ControlOutcome.proposed(
                applyFormationSlot(level, aircraft, phase, snapshot, profile, leader, members)), pilot.get(), level);''')
    return head + body + tail

def transform_arbiter(text):
    text = once(text, '        ControlOutcome formation = FormationFlightManager.applyControl(aircraft);', '''        FormationFlightManager.FormationEvaluation formationEvaluation = FormationFlightManager.evaluateWithPilot(aircraft);
        ControlOutcome formation = formationEvaluation.outcome();''')
    old = '''            if (formation.pendingWrite().isPresent()
                    && !attemptPendingWrite(aircraft, formation.pendingWrite().get())) {'''
    new = '''            if (formation.pendingWrite().isPresent()
                    && !attemptFormationPendingWrite(aircraft, formation.pendingWrite().get(), formationEvaluation)) {'''
    text = once(text, old, new)
    old = '''    private static boolean attemptPendingWrite(Entity aircraft, ControlProposal proposal) {
        if (aircraft.isRemoved() || aircraft.level().isClientSide || !MobPilotGate.isMobPiloted(aircraft)) {
            return false;
        }
        ReflectiveAircraft.applyControl(aircraft, proposal.x(), proposal.y(), proposal.z(),
                proposal.engineTarget());
        return true;
    }'''
    new = old + '''

    private static boolean attemptFormationPendingWrite(Entity aircraft, ControlProposal proposal,
                                                        FormationFlightManager.FormationEvaluation formation) {
        if (aircraft.isRemoved()) {
            return false;
        }
        var level = aircraft.level();
        if (level.isClientSide) {
            return false;
        }
        var pilot = MobPilotGate.pilotOf(aircraft);
        if (pilot.isEmpty() || formation == null
                || pilot.get() != formation.pilot() || level != formation.level()) {
            return false;
        }
        ReflectiveAircraft.applyControl(aircraft, proposal.x(), proposal.y(), proposal.z(),
                proposal.engineTarget());
        return true;
    }'''
    return once(text, old, new)

# Include source bytes of the existing fixture rather than import a potentially cached .pyc.
fixture_env = {'__name__': 'formation_owner_fixture', '__file__': str(BASE)}
exec(compile(BASE.read_bytes(), str(BASE), 'exec'), fixture_env)
STUBS = dict(fixture_env['STUBS'])
CASES = fixture_env['CASES']

def instrument_stubs():
    entity = STUBS['net/minecraft/world/entity/Entity.java']
    entity = once(entity, 'public UUID id;', '''public static final java.util.List<String> getterTrace=new java.util.ArrayList<>();
public static String inject=""; public static Runnable callback; public static final RuntimeException RUNTIME_SENTINEL=new RuntimeException("synthetic-getter-runtime");
public static final AssertionError ERROR_SENTINEL=new AssertionError("synthetic-getter-error");
static String caller(){boolean p=false;for(StackTraceElement x:Thread.currentThread().getStackTrace()){String c=x.getClassName();if(c.equals("com.wwdebug.autopilot.MobPilotGate")&&x.getMethodName().equals("pilotOf"))p=true;if(c.equals("com.wwdebug.autopilot.FormationFlightManager"))return p?"pilotOf-formation":"formation";if(c.equals("com.wwdebug.autopilot.ControlAuthorityArbiter")){boolean w=x.getMethodName().equals("attemptPendingWrite")||x.getMethodName().equals("attemptFormationPendingWrite");return p?(w?"pilotOf-pending":"pilotOf-arbiter"):(w?"pending":"arbiter");}}return p?"pilotOf-other":"other";}
static void recordGetter(String kind){String where=caller();getterTrace.add(kind+":"+where); if(inject.equals(kind+":"+where+":runtime"))throw RUNTIME_SENTINEL; if(inject.equals(kind+":"+where+":error"))throw ERROR_SENTINEL; if(inject.equals(kind+":"+where+":callback")&&callback!=null){Runnable c=callback;callback=null;c.run();}}
public UUID id;''')
    entity = once(entity, 'public Level level(){return world;}', 'public Level level(){recordGetter("level");return world;}')
    entity = once(entity, 'getControllingPassenger(){return pilot;}', 'getControllingPassenger(){recordGetter("pilot");return pilot;}')
    STUBS['net/minecraft/world/entity/Entity.java'] = entity
    probe = STUBS['com/wwdebug/autopilot/Probe.java']
    probe = once(probe, 'String c=args[0];ServerLevel l=', '''String c=args[0];
  Thread.setDefaultUncaughtExceptionHandler((t,e)->{System.out.println("uncaught_runtime_identity="+(e==Entity.RUNTIME_SENTINEL)+" uncaught_error_identity="+(e==Entity.ERROR_SENTINEL));System.out.println("getter_trace="+Entity.getterTrace);e.printStackTrace();System.exit(42);});
  Entity.inject=System.getProperty("fixture.inject","");
  if(c.equals("wrapper-empty")||c.equals("wrapper-populated")){
   ServerLevel w=new ServerLevel();Entity e=new Entity(new UUID(0,2),w);e.pilot=new Mob();
   if(c.equals("wrapper-populated")){AutonomousFlightManager.applyControl(e);Entity.getterTrace.clear();}
   ControlOutcome result=FormationFlightManager.applyControl(e);System.out.println("wrapper_outcome="+result.authority()+" getter_trace="+Entity.getterTrace);if(c.equals("wrapper-empty")&&result.claimed())throw new AssertionError("missing session was claimed");return;
  }
  ServerLevel l=''')
    probe = once(probe, 'var authority=ControlAuthorityArbiter.applyControl(a);boolean riskNow=',
                 'Entity.callback=()->{a.pilot=pilotB;AutopilotLogManager.events.add("synthetic-getter-callback-swap");};var authority=ControlAuthorityArbiter.applyControl(a);System.out.println("getter_trace="+Entity.getterTrace);boolean riskNow=')
    probe = once(probe, '  if(c.equals("collision")){', '''  if(System.getProperty("fixture.inject", "").endsWith(":callback")) {
    check(a.pilot==pilotB, "callback did not switch to B");
    if(ReflectiveAircraft.pilots.size()>1) check(ReflectiveAircraft.pilots.get(1)==pilotB, "second setter pilot was not B");
    check(ReflectiveAircraft.writes.size()==1, "CONTRACT: no pending setter after getter callback changes pilot");
    check(authority==ControlAuthorityArbiter.Authority.NONE && marker.get(a.getUUID())==ControlAuthorityArbiter.Authority.ENERGY_FIGHTER_REENGAGEMENT, "callback rejection authority/marker");
    System.out.println("classification=CALLBACK_CONTRACT_GREEN");return;
  }
  if(c.equals("collision")){''')
    STUBS['com/wwdebug/autopilot/Probe.java'] = probe
    STUBS['com/wwdebug/autopilot/GuardProbe.java']='''package com.wwdebug.autopilot; import java.util.*; import net.minecraft.server.level.ServerLevel; import net.minecraft.world.entity.*; public class GuardProbe { public static void main(String[] a)throws Exception { Entity e=new Entity(new UUID(0,2),new ServerLevel());e.removed=true;e.pilot=new Mob();Entity.inject="level:pending:runtime";ControlProposal p=ControlProposal.ofRawInputs(ControlAuthorityArbiter.Authority.FORMATION,0,0,0,1,"x");var m=ControlAuthorityArbiter.class.getDeclaredMethod("attemptPendingWrite",Entity.class,ControlProposal.class);m.setAccessible(true);boolean result=(boolean)m.invoke(null,e,p);System.out.println("removed_result="+result+" getter_trace="+Entity.getterTrace);if(result||!Entity.getterTrace.isEmpty())throw new AssertionError("removed did not short circuit");try{Class<?> f=Class.forName("com.wwdebug.autopilot.FormationFlightManager$FormationEvaluation");var fm=ControlAuthorityArbiter.class.getDeclaredMethod("attemptFormationPendingWrite",Entity.class,ControlProposal.class,f);fm.setAccessible(true);boolean fr=(boolean)fm.invoke(null,e,p,null);System.out.println("formation_removed_result="+fr+" getter_trace="+Entity.getterTrace);if(fr||!Entity.getterTrace.isEmpty())throw new AssertionError("formation removed did not short circuit");}catch(ClassNotFoundException absent){System.out.println("formation_helper_absent=baseline");} } }'''


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mode',choices=('baseline','candidate'),required=True)
    p.add_argument('--java-home',type=pathlib.Path,required=True)
    p.add_argument('--dependencies-json',type=pathlib.Path,required=True)
    p.add_argument('--output',type=pathlib.Path,required=True)
    a=p.parse_args(); out=a.output.absolute();out.mkdir(mode=0o700)
    src=out/'source-copy';fake=out/'stubs';classes=out/'classes';empty=out/'empty'
    for q in (src,fake,classes,empty):q.mkdir()
    jdk=a.java_home.resolve()/'bin';depsfile=a.dependencies_json.resolve();deps=[pathlib.Path(x) for x in json.loads(depsfile.read_text())]
    if not deps or any(not d.is_absolute() or not d.exists() for d in deps):raise ValueError('absolute existing classpath required')
    names=['ControlAuthorityArbiter','FormationFlightManager','AirspaceSafetyProbe','MobPilotGate','ControlOutcome','ControlProposal','FlightControlOutput','FlightPhase','AutopilotSession','FlightProfile','AutonomousFlightManager']
    original=[ROOT/'com/wwdebug/autopilot'/(n+'.java') for n in names];copies=[]
    for source in original:
        text=source.read_text();modified=text
        if a.mode=='candidate' and source.stem=='FormationFlightManager': modified=transform_formation(text)
        if a.mode=='candidate' and source.stem=='ControlAuthorityArbiter': modified=transform_arbiter(text)
        target=src/source.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True);target.write_text(modified);copies.append(target)
        if modified!=text:(out/(source.stem+'.patch')).write_text(''.join(difflib.unified_diff(text.splitlines(True),modified.splitlines(True),fromfile='original/'+source.name,tofile='private-copy/'+source.name)))
    instrument_stubs();paths=[]
    for name,value in STUBS.items():
        target=fake/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(value);paths.append(target)
    def inventory(entries):
        result={}
        for entry in entries:
            files=sorted(f for f in entry.rglob('*') if f.is_file()) if entry.is_dir() else [entry]
            for item in files:result[str(item)]=digest(item)
        return result
    inputs=original+copies+paths+[jdk/'java',jdk/'javac',depsfile,BASE,pathlib.Path(__file__).resolve()]
    before=inventory(inputs);cpbefore=inventory(deps);shutil.copyfile(__file__,out/'runner-snapshot.py')
    report={'mode':a.mode,'scope':'Actual production source or explicitly patched copies; artificial entities, level, checkpoint, world, combat and setter. No runtime or native setter claim. Getter trace is synthetic observation.', 'inputs_before':before,'classpath_before':cpbefore,'runs':{}}
    def run(name,command):
        r=subprocess.run(command,cwd=out,capture_output=True,text=True,timeout=30);(out/(name+'.stdout')).write_text(r.stdout);(out/(name+'.stderr')).write_text(r.stderr);report['runs'][name]={'argv':command,'exit':r.returncode};print(name,r.returncode,flush=True);return r.returncode
    rc=run('compile',[str(jdk/'javac'),'-proc:none','--release','17','-cp',os.pathsep.join(map(str,deps)),'-sourcepath',str(empty),'-d',str(classes),*map(str,copies),*map(str,paths)])
    if rc==0:
        for case in (*CASES, 'wrapper-empty', 'wrapper-populated'):
            run(case,[str(jdk/'java'),'-Xmx128m','-Xverify:all','-Xlog:class+load=info:file='+str(out/(case+'.classes.log')),'-cp',str(classes)+os.pathsep+os.pathsep.join(map(str,deps)),'com.wwdebug.autopilot.Probe',case])
        for kind in ('runtime','error'):
            for site in ('pilot:pilotOf-formation','level:formation','pilot:pilotOf-arbiter','level:arbiter','pilot:pilotOf-pending','level:pending'):
                name='inject-'+site.replace(':','-')+'-'+kind
                run(name,[str(jdk/'java'),'-Xmx128m','-Xverify:all','-Dfixture.inject='+site+':'+kind,'-Xlog:class+load=info:file='+str(out/(name+'.classes.log')),'-cp',str(classes)+os.pathsep+os.pathsep.join(map(str,deps)),'com.wwdebug.autopilot.Probe','formation-same'])
            for site in ('pilot:pilotOf-pending','level:pending'):
                name='combat-inject-'+site.replace(':','-')+'-'+kind
                run(name,[str(jdk/'java'),'-Xmx128m','-Xverify:all','-Dfixture.inject='+site+':'+kind,'-Xlog:class+load=info:file='+str(out/(name+'.classes.log')),'-cp',str(classes)+os.pathsep+os.pathsep.join(map(str,deps)),'com.wwdebug.autopilot.Probe','combat-same'])
        run('removed-short-circuit',[str(jdk/'java'),'-Xmx128m','-Xverify:all','-Xlog:class+load=info:file='+str(out/'removed-short-circuit.classes.log'),'-cp',str(classes)+os.pathsep+os.pathsep.join(map(str,deps)),'com.wwdebug.autopilot.GuardProbe'])
        run('pending-level-callback',[str(jdk/'java'),'-Xmx128m','-Xverify:all','-Dfixture.inject=level:pending:callback','-Xlog:class+load=info:file='+str(out/'pending-level-callback.classes.log'),'-cp',str(classes)+os.pathsep+os.pathsep.join(map(str,deps)),'com.wwdebug.autopilot.Probe','formation-same'])
    report['inputs_after']=inventory(inputs);report['inputs_unchanged']=before==report['inputs_after'];report['classpath_after']=inventory(deps);report['classpath_unchanged']=cpbefore==report['classpath_after'];report['compiled_classes']=inventory([classes]);report['runner_snapshot_sha256']=digest(out/'runner-snapshot.py');(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    # Existing combat swaps intentionally remain red; candidate is not a whole-stack fix.
    return 0 if report['inputs_unchanged'] and report['classpath_unchanged'] and len(report['runs'])==len(CASES)+21 and all(x['exit']==0 for x in report['runs'].values()) else 1
if __name__=='__main__':sys.exit(main())
