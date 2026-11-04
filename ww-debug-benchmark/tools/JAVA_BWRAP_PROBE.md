# Owned-fixture Java namespace observation

This test-only tool starts one cooperating Java 17 process. It does not start Minecraft, Forge,
a MOD, a server or GameTest, and it contacts no public endpoint. It does not establish safety or
permission to start any of them. It is for Linux systems with `/usr/bin/bwrap`, Python 3, a local
JDK 17 and support for unprivileged user, network, PID and mount namespaces.

The local `javac` runs **on the host before bubblewrap**, inheriting its environment. Use a
trusted JDK and inspect the compile environment (including Java tool/agent options) before
running it. `-proc:none` does not establish compiler or environment isolation.

The earlier Python-only namespace observations did not measure a Java process. This probe
records Java's class/resource reads, its own output, selected namespace/FD/mount information,
and connections only to owned sockets. It uses `--unshare-user --unshare-net --unshare-pid`,
`--die-with-parent`, `--cap-drop ALL`, read-only mounts for `/usr`, the JDK and the test inputs,
and dedicated writable output and tmpfs. It clears the child environment. No authentication,
runner, host network policy or existing world is modified.

Run from the repository root, providing a local JDK and a **new, non-existing** output directory:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 ww-debug-benchmark/tools/run_owned_java_bwrap_probe.py \
  --java-home /absolute/path/to/jdk-17 --output /absolute/path/to/new-owned-evidence
```

An existing output path is rejected; the tool never purges or reuses one. If prerequisites fail,
keep the output and error as evidence; do not retry without the namespace isolation. `compile.json`,
`java-run.json`, `parent.json`, `observation.json` and `output/` record argv, selected input hashes,
results and child mount information. Compile or setup failure may leave only partial records.
To restore the project, revert the commit adding this tool. Keep prior output and failure records;
no world, cache or existing evidence must be deleted.

The parent binds owned host-network IPv4 and IPv6 loopback listeners. Child attempts to those
ports must fail, and the parent listener must not be ready at the subsequent check. Positive TCP
controls bind and connect to separate owned IPv4 and IPv6 loopback ports **inside the same Java
process**; the UNIX-socket positive control is likewise a self-connection. The post-run readiness
check is not a packet trace. `/proc/net/route` and `ipv6_route` are recorded, not evaluated as an
exhaustive network policy. No public-network or arbitrary external egress test is performed.
The check treats any connection or read-only-open `IOException` as rejection, so inspect the raw
exception: an unrelated error can also produce a green result.

These observations apply only to the cooperating process and inputs used. They do not authenticate
all JDK or `/usr` content, observe policy routing or every FD throughout execution, establish the
origin of every socket, exercise a separate Java supervisor, test seccomp, output or inode limits,
or prove cleanup of descendant processes. A false `Files.exists` can mean inaccessible. Some mounts
besides the output are writable; the child can read the whole mounted `/usr`. The JDK `java`,
`javac`, `lib/modules`, `lib/server/libjvm.so`, `bwrap`, source and fixture bytes are hashed from
after compilation to after the child run, not over the complete JDK or compilation itself. Any
unobserved condition remains unknown; these checks cannot authorize a real-world test.
