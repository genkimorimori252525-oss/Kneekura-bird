#!/usr/bin/env bash
# Offline, standalone experiment. Output must be a new directory outside this repository.
set -euo pipefail
: "${JAVA_HOME:?Set JAVA_HOME to JDK 17}"
: "${GRADLE_USER_HOME:?Set GRADLE_USER_HOME to the fixed Forge cache}"
[[ $# == 1 ]] || { echo 'usage: build.sh NEW_OUTPUT_DIRECTORY' >&2; exit 2; }
root=$(cd "$(dirname "$0")/../.." && pwd -P)
out=$(realpath -m "$1")
[[ "$out" != "$root" && "$out" != "$root/"* && ! -e "$out" && ! -L "$1" ]] || { echo 'output must be new and outside repository' >&2; exit 2; }
[[ $("$JAVA_HOME/bin/javac" -version 2>&1) == 'javac 17.'* ]] || { echo 'JDK 17 required' >&2; exit 2; }
cache="$GRADLE_USER_HOME/caches"
[[ -d "$cache" ]] || { echo 'missing cache' >&2; exit 2; }
mkdir "$out"
mkdir "$out/classes" "$out/test-classes"
cpfile="$out/classpath.txt"
python3 - "$cache" "$cpfile" <<'PY'
import pathlib, sys, zipfile
root = pathlib.Path(sys.argv[1])
jars = sorted(p for p in root.rglob('*.jar') if not p.name.endswith(('-sources.jar', '-javadoc.jar')) and zipfile.is_zipfile(p))
def exactly(prefix):
    hits = [p for p in jars if p.name == prefix]
    if len(hits) != 1: raise SystemExit('fixed mapped dependency missing or ambiguous: ' + prefix)
    return hits[0]
first = [exactly('forge-1.20.1-47.4.20_mapped_official_1.20.1.jar'), exactly('immersive_aircraft-1.3.3+1.20.1-forge_mapped_official_1.20.1.jar')]
if any(':' in str(p) or '\n' in str(p) for p in jars): raise SystemExit('invalid classpath')
pathlib.Path(sys.argv[2]).write_text(':'.join(map(str, first + [p for p in jars if p not in first])))
PY
src="$root/tools/native-input-observer/src"
"$JAVA_HOME/bin/javac" -proc:none --release 17 -cp "$(cat "$cpfile")" -d "$out/classes" "$src"/main/java/com/wwdebug/probe/input/*.java "$src"/main/java/com/wwdebug/probe/input/mixin/*.java
"$JAVA_HOME/bin/javac" -proc:none --release 17 -cp "$out/classes" -d "$out/test-classes" "$src/test/java/com/wwdebug/probe/input/TraceBufferTest.java"
"$JAVA_HOME/bin/java" -cp "$out/classes:$out/test-classes" com.wwdebug.probe.input.TraceBufferTest
"$JAVA_HOME/bin/jar" --create --file "$out/wwdebug-input-probe.jar" --manifest "$src/main/resources/META-INF/MANIFEST.MF" -C "$out/classes" . -C "$src/main/resources" wwdebug_input_probe.mixins.json -C "$src/main/resources" META-INF/mods.toml
python3 - "$out/wwdebug-input-probe.jar" <<'PY'
import json, sys, zipfile
with zipfile.ZipFile(sys.argv[1]) as z:
    names = [n for n in z.namelist() if not n.endswith('/')]
    assert len(names) == len(set(names))
    extras = {'META-INF/MANIFEST.MF', 'META-INF/mods.toml', 'wwdebug_input_probe.mixins.json'}
    classes = [n for n in names if n.endswith('.class')]
    assert classes and all(n.startswith('com/wwdebug/probe/input/') and n.rsplit('/', 1)[1].split('$')[0].split('.')[0] in {'TraceBuffer', 'NativeInputObserver', 'ObserverMod', 'VehicleInputMixin'} for n in classes)
    assert set(names) == extras | set(classes)
    assert b'MixinConfigs: wwdebug_input_probe.mixins.json' in z.read('META-INF/MANIFEST.MF')
    cfg = json.loads(z.read('wwdebug_input_probe.mixins.json'))
    assert cfg['required'] and cfg['package'] == 'com.wwdebug.probe.input.mixin' and cfg['mixins'] == ['VehicleInputMixin']
    assert 'com/wwdebug/probe/input/mixin/VehicleInputMixin.class' in classes
    assert all(n == 'com/wwdebug/probe/input/mixin/VehicleInputMixin.class' for n in classes if '/mixin/' in n)
    assert b'modId="wwdebug_input_probe"' in z.read('META-INF/mods.toml')
print('JAR contents PASS (runtime loading and transformation not tested)')
PY
sha256sum "$out/wwdebug-input-probe.jar"
