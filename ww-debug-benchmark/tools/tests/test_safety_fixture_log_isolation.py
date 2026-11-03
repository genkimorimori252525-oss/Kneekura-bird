"""Exercise the test-only log isolator with independent, buffered stub writers."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


HELPER = (Path(__file__).resolve().parents[2] / "src/main/java/com/wwdebug/autopilot"
          / "SafetyFixtureLogIsolation.java")
SERVER = "package net.minecraft.server; public class MinecraftServer {}"
ARBITER = """package com.wwdebug.autopilot;
import java.util.*;
public class ControlAuthorityArbiter { private static final Map<UUID,Object> LAST_AUTHORITY = new HashMap<>(); }
"""
LOGGER = """package com.wwdebug.autopilot;
import java.io.*;
import java.nio.file.*;
import java.util.*;
import net.minecraft.server.MinecraftServer;
public class AutopilotLogManager {
  private static final Map<MinecraftServer,RunLog> RUNS = new IdentityHashMap<>();
  static RunLog register(MinecraftServer server, Path path, boolean failFlush) throws IOException {
    RunLog run = new RunLog(path, failFlush); RUNS.put(server, run); return run;
  }
  static class RunLog {
    private final Path directory;
    private final BufferedWriter combined;
    private final Map<UUID,AircraftWriter> aircraftWriters = new HashMap<>();
    private final Map<UUID,Object> motionSamples = new HashMap<>();
    RunLog(Path p, boolean failFlush) throws IOException {
      directory=p;
      combined=failFlush ? new BufferedWriter(new StringWriter()) {
        @Override public void flush() throws IOException { throw new IOException("flush failure"); }
      } : Files.newBufferedWriter(p.resolve("combined.jsonl"));
    }
    void combined(String value) throws IOException { combined.write(value); combined.newLine(); }
    void partialCombined(String value) throws IOException { combined.write(value); }
    void open(UUID id, String value) throws IOException {
      BufferedWriter out=Files.newBufferedWriter(directory.resolve("aircraft/test-"+id+".jsonl"),
          StandardOpenOption.CREATE, StandardOpenOption.APPEND);
      out.write(value); out.newLine(); aircraftWriters.put(id,new AircraftWriter(out));
    }
    void openWithCloseFailure(UUID id, String value) throws IOException {
      BufferedWriter out=new BufferedWriter(Files.newBufferedWriter(
          directory.resolve("aircraft/test-"+id+".jsonl"), StandardOpenOption.CREATE,
          StandardOpenOption.APPEND)) {
        @Override public void close() throws IOException { throw new IOException("close failure"); }
      };
      out.write(value); out.newLine(); aircraftWriters.put(id,new AircraftWriter(out));
    }
    boolean hasWriter(UUID id) { return aircraftWriters.containsKey(id); }
    void append(UUID id, String value) throws IOException {
      aircraftWriters.get(id).writer.write(value); aircraftWriters.get(id).writer.newLine();
    }
    void close(UUID id) throws IOException { aircraftWriters.remove(id).writer.close(); }
  }
  static class AircraftWriter { private final BufferedWriter writer; AircraftWriter(BufferedWriter w) {writer=w;} }
}
"""
HARNESS = r'''package com.wwdebug.autopilot;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import net.minecraft.server.MinecraftServer;
public class IsolationHarness {
  static void check(boolean ok, String reason) { if (!ok) throw new AssertionError(reason); }
  static String row(UUID id, int n) { return "{\"aircraft_uuid\":\""+id+"\",\"n\":"+n+"}"; }
  public static void main(String[] args) throws Exception {
    String test=args[0]; UUID id=UUID.randomUUID(), other=UUID.randomUUID();
    MinecraftServer server=new MinecraftServer(); Path root=Files.createTempDirectory("isolation-unit-");
    Files.createDirectories(root.resolve("aircraft"));
    AutopilotLogManager.RunLog run=AutopilotLogManager.register(server,root,test.equals("flush_failure"));
    String a=row(id,1), b=row(id,2), unrelated=row(other,9);
    Path source=root.resolve("aircraft/test-"+id+".jsonl");
    if (test.equals("healthy_reopen")) {
      run.combined(a); run.open(id,a); run.close(id);
      run.combined(unrelated); run.open(other,unrelated); run.combined(b); run.open(id,b);
    } else if (test.equals("empty")) {
      Files.writeString(source,""); run.combined(unrelated);
    } else if (test.equals("missing_source")) {
      run.combined(a);
    } else if (test.equals("invalid_utf8")) {
      byte[] newline=System.lineSeparator().getBytes(StandardCharsets.UTF_8);
      byte[] invalid=new byte[newline.length+1]; invalid[0]=(byte)0xff;
      System.arraycopy(newline,0,invalid,1,newline.length);
      Files.write(source,invalid); run.combined(a);
    } else if (test.equals("missing_combined")) {
      run.open(id,a); run.combined(unrelated);
    } else if (test.equals("mismatch")) {
      run.open(id,a); run.combined(a); run.combined(b);
    } else if (test.equals("wrong_order")) {
      run.open(id,a); run.close(id); run.open(id,b); run.combined(b); run.combined(a);
    } else if (test.equals("extra_individual")) {
      run.open(id,a); run.close(id); run.open(id,b); run.combined(a);
    } else if (test.equals("partial_individual")) {
      Files.writeString(source,a); run.combined(a);
    } else if (test.equals("partial_combined")) {
      run.open(id,a); run.partialCombined(a);
    } else if (test.equals("malformed_combined")) {
      run.open(id,a); run.combined(a); run.combined("{broken");
    } else if (test.equals("missing_identity")) {
      run.open(id,a); run.combined(a); run.combined("{\"n\":42}");
    } else if (test.equals("duplicate")) {
      run.open(id,a); run.combined(a);
      Files.writeString(root.resolve("aircraft/second-"+id+".jsonl"),a+System.lineSeparator());
    } else if (test.equals("destination_conflict")) {
      run.open(id,a); run.combined(a); Files.createDirectory(root.resolve("fixture-aircraft"));
      Files.writeString(root.resolve("fixture-aircraft/test-"+id+".jsonl"),"existing");
    } else if (test.equals("destination_io")) {
      run.open(id,a); run.combined(a); Files.writeString(root.resolve("fixture-aircraft"),"blocked");
    } else if (test.equals("flush_failure")) {
      run.open(id,a);
    } else if (test.equals("close_failure")) {
      run.openWithCloseFailure(id,a); run.combined(a);
    } else { throw new AssertionError("unknown case"); }

    boolean failed=false;
    try { SafetyFixtureLogIsolation.isolate(server,id); }
    catch (IllegalStateException expected) { failed=true; }
    Path dest=root.resolve("fixture-aircraft/test-"+id+".jsonl");
    if (test.equals("healthy_reopen")) {
      check(!failed,"healthy two-session fixture failed");
      check(run.hasWriter(other),"unrelated writer was removed");
      run.append(other,row(other,10));
      run.close(other);
      check(Files.exists(root.resolve("aircraft/test-"+other+".jsonl")),"unrelated log was moved");
      String nl=System.lineSeparator();
      check(Files.readString(root.resolve("aircraft/test-"+other+".jsonl"))
          .equals(unrelated+nl+row(other,10)+nl),"unrelated writer did not remain usable");
      check(Files.readString(dest).equals(a+nl+b+nl),"fixture rows were not preserved");
      check(Files.readString(root.resolve("combined.jsonl")).equals(a+nl+unrelated+nl+b+nl),
          "combined was not flushed or was altered");
      check(!Files.exists(source),"source remained in ordinary aircraft directory");
    } else {
      check(failed,"corrupt or unflushable logs were accepted: "+test);
      if (!test.equals("missing_source")) {
        check(Files.exists(source),"source log was removed after failure: "+test);
      }
      if (test.equals("destination_conflict")) {
        check(Files.readString(dest).equals("existing"),"existing destination was overwritten");
      } else if (!test.equals("destination_io")) {
        check(!Files.exists(dest),"destination created after failure: "+test);
      }
      if (test.equals("duplicate")) {
        check(Files.exists(root.resolve("aircraft/second-"+id+".jsonl")),"duplicate was removed");
      }
      if (test.equals("close_failure")) {
        check(run.hasWriter(id),"failed writer was removed from logger management");
      }
    }
  }
}
'''


class SafetyFixtureLogIsolationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        java_home = os.environ.get("JAVA_HOME")
        suffix = ".exe" if os.name == "nt" else ""
        cls.javac = str(Path(java_home) / "bin" / ("javac" + suffix)) if java_home else shutil.which("javac")
        cls.java = str(Path(java_home) / "bin" / ("java" + suffix)) if java_home else shutil.which("java")
        gson = os.environ.get("WW_TEST_GSON_JAR")
        if not cls.javac or not cls.java or not gson or not Path(gson).is_file():
            raise unittest.SkipTest("Java 17 and WW_TEST_GSON_JAR are required")
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        base = root / "src/com/wwdebug/autopilot"
        base.mkdir(parents=True)
        server = root / "src/net/minecraft/server"
        server.mkdir(parents=True)
        (server / "MinecraftServer.java").write_text(SERVER, encoding="utf-8")
        (base / "ControlAuthorityArbiter.java").write_text(ARBITER, encoding="utf-8")
        (base / "AutopilotLogManager.java").write_text(LOGGER, encoding="utf-8")
        (base / "IsolationHarness.java").write_text(HARNESS, encoding="utf-8")
        shutil.copyfile(HELPER, base / HELPER.name)
        cls.classes = root / "classes"
        cls.classes.mkdir()
        cls.classpath = os.pathsep.join((str(cls.classes), gson))
        subprocess.run([cls.javac, "-cp", gson, "-d", str(cls.classes),
                        *(str(path) for path in (root / "src").rglob("*.java"))], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def check_case(self, name, line_separator=None):
        java_options = [] if line_separator is None else ["-Dline.separator=" + line_separator]
        result = subprocess.run([self.java, *java_options, "-cp", self.classpath,
                                 "com.wwdebug.autopilot.IsolationHarness", name],
                                text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_two_sessions_and_unrelated_rows_are_preserved(self):
        self.check_case("healthy_reopen")

    def test_two_sessions_with_windows_line_endings(self):
        self.check_case("healthy_reopen", "\r\n")

    def test_empty_individual_log_is_rejected(self):
        self.check_case("empty")

    def test_missing_individual_log_is_rejected(self):
        self.check_case("missing_source")

    def test_unreadable_individual_row_is_rejected(self):
        self.check_case("invalid_utf8")

    def test_missing_combined_rows_are_rejected(self):
        self.check_case("missing_combined")

    def test_incomplete_individual_log_is_rejected(self):
        self.check_case("mismatch")

    def test_reordered_individual_log_is_rejected(self):
        self.check_case("wrong_order")

    def test_combined_flush_failure_is_rejected(self):
        self.check_case("flush_failure")

    def test_individual_close_failure_keeps_writer_registered(self):
        self.check_case("close_failure")

    def test_extra_individual_rows_are_rejected(self):
        self.check_case("extra_individual")

    def test_missing_individual_final_newline_is_rejected(self):
        self.check_case("partial_individual")

    def test_missing_combined_final_newline_is_rejected(self):
        self.check_case("partial_combined")

    def test_malformed_combined_row_is_rejected(self):
        self.check_case("malformed_combined")

    def test_combined_row_without_identity_is_rejected(self):
        self.check_case("missing_identity")

    def test_duplicate_logs_are_preserved_and_rejected(self):
        self.check_case("duplicate")

    def test_existing_destination_is_preserved_and_rejected(self):
        self.check_case("destination_conflict")

    def test_destination_io_failure_preserves_source(self):
        self.check_case("destination_io")


if __name__ == "__main__":
    unittest.main()
