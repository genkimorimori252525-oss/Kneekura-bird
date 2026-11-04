#!/usr/bin/env python3
"""Inspect a public descriptor in saved source-copy classes; no MOD is run."""
import argparse, hashlib, json, pathlib, subprocess, sys

def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline',type=pathlib.Path,required=True)
    parser.add_argument('--candidate',type=pathlib.Path,required=True)
    parser.add_argument('--java-home',type=pathlib.Path,required=True)
    parser.add_argument('--output',type=pathlib.Path,required=True)
    a=parser.parse_args();out=a.output.absolute();out.mkdir(mode=0o700)
    javap=a.java_home.resolve()/'bin/javap';script=pathlib.Path(__file__).resolve()
    report={'scope':'Static source-copy compiled class only; no runtime compatibility claim.','javap':str(javap),'javap_sha256':digest(javap),'script_sha256':digest(script),'runs':{}}
    for mode,root in (('baseline',a.baseline),('candidate',a.candidate)):
        cls=root.resolve()/'classes/com/wwdebug/autopilot/FormationFlightManager.class';before=digest(cls)
        argv=[str(javap),'-p','-s',str(cls)];r=subprocess.run(argv,capture_output=True,text=True,timeout=30)
        stdout=out/(mode+'.stdout');stderr=out/(mode+'.stderr');stdout.write_text(r.stdout);stderr.write_text(r.stderr)
        report['runs'][mode]={'argv':argv,'exit':r.returncode,'class_before':before,'class_after':digest(cls),'stdout_sha256':digest(stdout),'stderr_sha256':digest(stderr)}
    report['javap_sha256_after']=digest(javap);report['script_sha256_after']=digest(script)
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    ok=report['javap_sha256']==report['javap_sha256_after'] and report['script_sha256']==report['script_sha256_after'] and all(r['exit']==0 and r['class_before']==r['class_after'] for r in report['runs'].values())
    print('descriptor inspection', 'complete' if ok else 'inconclusive');return 0 if ok else 1
if __name__=='__main__':sys.exit(main())
