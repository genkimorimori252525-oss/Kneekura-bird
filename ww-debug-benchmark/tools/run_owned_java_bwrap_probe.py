#!/usr/bin/env python3
"""Launch one cooperating Java process in new namespaces; no MOD/server/world."""
import argparse, hashlib, json, os, pathlib, select, socket, subprocess, sys
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--java-home', type=pathlib.Path, required=True)
parser.add_argument('--output', type=pathlib.Path, required=True,
                    help='new, non-existing directory for this run')
args = parser.parse_args()
script = pathlib.Path(__file__).resolve()
source = script.with_name('OwnedJavaProbe.java')
jdk = args.java_home.resolve(strict=True)
p = args.output.absolute()
p.mkdir(mode=0o700, exist_ok=False)
inputs = p/'input'; output = p/'output'; private = p/'parent-private'
for d in (inputs, output, private): d.mkdir(mode=0o700, exist_ok=False)
resource = inputs/'owned-resource.txt'; resource.write_text('owned classpath resource 1\n')
marker = private/'owned-marker'; marker.write_text('owned private marker\n')
markerfd = os.open(marker, os.O_RDONLY|os.O_CLOEXEC)
def sha(f):
 h=hashlib.sha256()
 with f.open('rb') as inp:
  for b in iter(lambda:inp.read(1024*1024), b''): h.update(b)
 return h.hexdigest()
def invoke(name, cmd, **kwargs):
 try:
  r=subprocess.run(cmd,capture_output=True,text=True,timeout=20,close_fds=True,**kwargs)
  result={'argv':list(map(str,cmd)),'exit':r.returncode,'stdout':r.stdout,'stderr':r.stderr}
 except subprocess.TimeoutExpired as exc:
  result={'argv':list(map(str,cmd)),'timeout':True,'stdout':str(exc.stdout),'stderr':str(exc.stderr)}
 (p/(name+'.json')).write_text(json.dumps(result,indent=2)+'\n'); return result
compile_result=invoke('compile',[str(jdk/'bin/javac'),'-proc:none','--release','17','-classpath',str(inputs),'-sourcepath',str(inputs),'-d',str(inputs),str(source)])
if compile_result.get('exit')!=0: sys.exit(1)
listeners={}
try:
 for name,family,addr in [('ipv4',socket.AF_INET,('127.0.0.1',0)),('ipv6',socket.AF_INET6,('::1',0))]:
  s=socket.socket(family,socket.SOCK_STREAM)
  if family==socket.AF_INET6:s.setsockopt(socket.IPPROTO_IPV6,socket.IPV6_V6ONLY,1)
  s.bind(addr);s.listen(1);s.setblocking(False);listeners[name]=s
 parent={'pid':os.getpid(),'fd':markerfd,'marker':str(marker),'v4port':listeners['ipv4'].getsockname()[1],'v6port':listeners['ipv6'].getsockname()[1], 'namespaces':{k:os.readlink('/proc/self/ns/'+k) for k in ('net','user','mnt','pid')}}
 (p/'parent.json').write_text(json.dumps(parent,indent=2)+'\n')
 before={str(f):sha(f) for f in [script,source,resource,inputs/'OwnedJavaProbe.class',marker,jdk/'bin/java',jdk/'bin/javac',jdk/'lib/modules',jdk/'lib/server/libjvm.so',pathlib.Path('/usr/bin/bwrap')]}
 cmd=['/usr/bin/bwrap','--unshare-user','--unshare-net','--unshare-pid','--die-with-parent','--cap-drop','ALL','--ro-bind','/usr','/usr','--symlink','usr/lib','/lib','--symlink','usr/lib64','/lib64','--proc','/proc','--dev','/dev','--ro-bind',str(jdk),'/jdk','--ro-bind',str(inputs),'/probe-input','--bind',str(output),'/probe-output','--tmpfs','/tmp','--chdir','/probe-output','--clearenv','--setenv','PATH','/usr/bin','/jdk/bin/java','-Xmx64m','-cp','/probe-input','OwnedJavaProbe',str(parent['v4port']),str(parent['v6port']),str(marker),str(parent['pid']),str(parent['fd'])]
 run=invoke('java-run',cmd,stdin=subprocess.DEVNULL)
 ready={name:bool(select.select([s],[],[],0)[0]) for name,s in listeners.items()}
 after={key:sha(pathlib.Path(key)) for key in before}
 lines=run['stdout'].splitlines(); observed=dict(line.split('=',1) for line in lines if '=' in line)
 checks={'java_exited_zero':run.get('exit')==0, 'inputs_unchanged':before==after,
         'java_runtime_17':observed.get('runtime','').split('.')[0].split('+')[0]=='17',
         'namespace_ids_differ':all(observed.get('namespace_'+k)!=v and observed.get('namespace_'+k) is not None for k,v in parent['namespaces'].items()),
         'workspace_hidden':observed.get('workspace_visible')=='false', 'parent_marker_hidden':observed.get('parent_owned_marker_visible')=='false',
         'parent_fd_hidden':observed.get('parent_fd_visible')=='false', 'parent_root_hidden':observed.get('parent_root_visible')=='false',
         'input_not_opened_for_write':bool(observed.get('readonly_open')) and observed.get('readonly_open')!='UNEXPECTED_ALLOWED',
         'jdk_not_opened_for_write':bool(observed.get('jdk_readonly_open')) and observed.get('jdk_readonly_open')!='UNEXPECTED_ALLOWED',
         'resource_read':observed.get('classpath_resource')=='owned classpath resource 1', 'owned_unix_socket_positive':observed.get('owned_unix_positive')=='true',
         'owned_ipv4_positive':observed.get('owned_ipv4_positive','').startswith('PASS:port='), 'owned_ipv6_positive':observed.get('owned_ipv6_positive','').startswith('PASS:port='),
         'host_ipv4_listener_not_connected':observed.get('parent_ipv4_connect') not in (None,'CONNECTED') and not ready['ipv4'],
         'host_ipv6_listener_not_connected':observed.get('parent_ipv6_connect') not in (None,'CONNECTED') and not ready['ipv6'],
         'effective_caps_zero':observed.get('process_CapEff')=='0000000000000000', 'result_file_matches_stdout':(output/'result.txt').is_file() and (output/'result.txt').read_text()==run['stdout']}
 observation={'input_hashes_before':before,'input_hashes_after':after,'inputs_unchanged':before==after,'host_listener_ready_after':ready,'checks':checks,'scope':'One cooperating Java process with owned fixtures; no external endpoint contacted, no Minecraft/Forge/GameTest. Route listing is observational, not an exhaustive policy-routing/network proof. Host loopback connect attempts test cross-network-namespace isolation, not arbitrary public egress. Unmounted workspace check does not prove arbitrary sandbox security.','java_exit':run.get('exit'),'java_timeout':run.get('timeout',False)}
 (p/'observation.json').write_text(json.dumps(observation,indent=2)+'\n')
 print(json.dumps({'java_exit':run.get('exit'),'checks':checks,'host_listener_ready_after':ready}))
 sys.exit(0 if all(checks.values()) else 1)
except Exception as exc:
 (p/'setup-error.json').write_text(json.dumps({'exception_type':type(exc).__name__,'message':str(exc)},indent=2)+'\n')
 raise
finally:
 for s in listeners.values():s.close()
 os.close(markerfd)
