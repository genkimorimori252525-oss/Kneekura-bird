#!/usr/bin/env python3
"""Compare public descriptors in copied-source classes without running the MOD."""
import argparse,hashlib,json,pathlib,subprocess,sys

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--baseline',type=pathlib.Path,required=True);p.add_argument('--candidate',type=pathlib.Path,required=True);p.add_argument('--java-home',type=pathlib.Path,required=True);p.add_argument('--output',type=pathlib.Path,required=True);a=p.parse_args();out=a.output.absolute();out.mkdir(mode=0o700);javap=a.java_home.resolve()/'bin/javap';script=pathlib.Path(__file__).resolve();jbefore=sha(javap);sbefore=sha(script)
 targets={'AirCombatManeuverManager':'(Lnet/minecraft/world/entity/Entity;)Ljava/util/Optional;','FighterCombatFacade':'(Lnet/minecraft/world/entity/Entity;Z)Lcom/wwdebug/autopilot/ControlOutcome;','ControlAuthorityArbiter':'(Lnet/minecraft/world/entity/Entity;)Lcom/wwdebug/autopilot/ControlAuthorityArbiter$Authority;','FighterCombatFacade$CombatEvaluation':'(Lcom/wwdebug/autopilot/ControlOutcome;Lnet/minecraft/world/entity/Mob;Lnet/minecraft/server/level/ServerLevel;Z)V'};report={'scope':'Static source-copy class descriptors; the added record component can affect equals/hashCode/toString/reflection; runtime compatibility is not proven.','javap':str(javap),'javap_before':jbefore,'script_before':sbefore,'runs':{},'errors':[]}
 for mode,root in (('baseline',a.baseline),('candidate',a.candidate)):
  for name,descriptor in targets.items():
   cls=root.resolve()/'classes/com/wwdebug/autopilot'/(name+'.class');before=sha(cls);argv=[str(javap),'-p','-s',str(cls)];r=subprocess.run(argv,capture_output=True,text=True,timeout=30);out_file=out/(mode+'-'+name+'.stdout');err_file=out/(mode+'-'+name+'.stderr');out_file.write_text(r.stdout);err_file.write_text(r.stderr);lines=r.stdout.splitlines();matches=[]
   for i,line in enumerate(lines[:-1]):
    relevant=('applyControl(net.minecraft.world.entity.Entity' in line) if name!='FighterCombatFacade$CombatEvaluation' else ('CombatEvaluation(com.wwdebug.autopilot.ControlOutcome, net.minecraft.world.entity.Mob, net.minecraft.server.level.ServerLevel, boolean);' in line)
    if relevant and lines[i+1].strip()=='descriptor: '+descriptor:matches.append(line.strip())
   entry={'argv':argv,'exit':r.returncode,'class_before':before,'class_after':sha(cls),'stdout_sha256':sha(out_file),'stderr_sha256':sha(err_file),'expected_descriptor':descriptor,'matching_declarations':matches};report['runs'][mode+'-'+name]=entry
   if r.returncode or before!=entry['class_after'] or len(matches)!=1:report['errors'].append(mode+' '+name)
 report['javap_after']=sha(javap);report['script_after']=sha(script)
 if report['javap_after']!=jbefore or report['script_after']!=sbefore:report['errors'].append('inspection input changed')
 (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print('errors',len(report['errors']));return 1 if report['errors'] else 0
if __name__=='__main__':sys.exit(main())
