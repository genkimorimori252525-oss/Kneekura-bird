#!/usr/bin/env python3
"""Exercise the real wheel-lock source against minimal, deterministic stand-ins.

This is not a Minecraft/Forge test. It deliberately supplies synthetic BRAKE
status and occupants; it does not exercise session lifetime or cleanup.
WHEEL_LOCK_CLASSES_DIR executes class files from that directory: only point it
at a trusted local build. This test does not establish those files are safe.
"""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/main/java/com/wwdebug/autopilot"
STUBS = {
    "net/minecraft/world/level/Level.java": """
package net.minecraft.world.level;
public class Level { public boolean isClientSide; }
""",
    "net/minecraft/world/phys/Vec3.java": """
package net.minecraft.world.phys;
public class Vec3 {
    public final double x, y, z;
    public Vec3(double x, double y, double z) { this.x=x; this.y=y; this.z=z; }
    public double horizontalDistance() { return Math.sqrt(x*x + z*z); }
}
""",
    "net/minecraft/world/entity/Entity.java": """
package net.minecraft.world.entity;
import java.util.UUID;
import net.minecraft.world.level.Level;
import net.minecraft.world.phys.Vec3;
public class Entity {
    public final Level world = new Level();
    public boolean grounded = true;
    public LivingEntity pilot;
    public Vec3 velocity = new Vec3(0.03, -0.02, 0.0);
    public int writes;
    public Level level() { return world; }
    public boolean onGround() { return grounded; }
    public UUID getUUID() { return new UUID(0, 1); }
    public LivingEntity getControllingPassenger() { return pilot; }
    public Vec3 getDeltaMovement() { return velocity; }
    public void setDeltaMovement(double x, double y, double z) {
        writes++;
        velocity = new Vec3(x, y, z);
    }
}
""",
    "net/minecraft/world/entity/LivingEntity.java": """
package net.minecraft.world.entity;
public class LivingEntity extends Entity { }
""",
    "net/minecraft/world/entity/Mob.java": """
package net.minecraft.world.entity;
public class Mob extends LivingEntity { }
""",
    "net/minecraft/world/entity/player/Player.java": """
package net.minecraft.world.entity.player;
import net.minecraft.world.entity.LivingEntity;
public class Player extends LivingEntity { }
""",
    "com/wwdebug/autopilot/AutonomousFlightManager.java": """
package com.wwdebug.autopilot;
import java.util.Optional;
import java.util.UUID;
public class AutonomousFlightManager {
    public static SessionStatus status;
    public static Optional<SessionStatus> status(UUID id) { return Optional.ofNullable(status); }
    public record SessionStatus(UUID aircraftUuid, String aircraftName, String profileId,
        String doctrine, FlightPhase phase, int phaseTicks, int missionTicks,
        String transitionReason) { }
}
""",
    "com/wwdebug/autopilot/WheelLockHarness.java": """
package com.wwdebug.autopilot;
import java.util.UUID;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.entity.Mob;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.phys.Vec3;
public class WheelLockHarness {
    private static int failures;
    private static void check(String name, boolean ok, String details) {
        System.out.println((ok ? "PASS " : "FAIL ") + name + " " + details);
        if (!ok) failures++;
    }
    private static void status(FlightPhase phase) {
        AutonomousFlightManager.status = phase == null ? null :
            new AutonomousFlightManager.SessionStatus(new UUID(0,1), "fixture", "fixture",
                "fixture", phase, 0, 0, "fixture");
    }
    private static void run(String name, LivingEntity pilot, boolean client, boolean grounded,
                            FlightPhase phase, double x, double y, double z, boolean lock) {
        Entity aircraft = new Entity();
        aircraft.pilot = pilot;
        aircraft.world.isClientSide = client;
        aircraft.grounded = grounded;
        aircraft.velocity = new Vec3(x, y, z);
        status(phase);
        AutopilotWheelLockAdapter.apply(aircraft);
        Vec3 result = aircraft.getDeltaMovement();
        double wantX = lock ? 0.0 : x, wantY = lock ? Math.min(0.0, y) : y;
        double wantZ = lock ? 0.0 : z;
        int wantWrites = lock ? 1 : 0;
        boolean ok = aircraft.writes == wantWrites && result.x == wantX &&
                     result.y == wantY && result.z == wantZ;
        check(name, ok, "setter=" + aircraft.writes + " expected=" + wantWrites +
              " input=(" + x + "," + y + "," + z + ")" +
              " vector=(" + result.x + "," + result.y + "," + result.z + ")");
    }
    public static void main(String[] args) {
        Entity aircraft = new Entity();
        check("gate-empty", !MobPilotGate.isMobPiloted(aircraft) &&
              !MobPilotGate.isPlayerControlled(aircraft), "no occupant");
        aircraft.pilot = new Player();
        check("gate-player", !MobPilotGate.isMobPiloted(aircraft) &&
              MobPilotGate.isPlayerControlled(aircraft), "player");
        aircraft.pilot = new Mob();
        check("gate-mob", MobPilotGate.isMobPiloted(aircraft) &&
              !MobPilotGate.isPlayerControlled(aircraft), "mob");
        run("mob-brake", new Mob(), false, true, FlightPhase.BRAKE, 0.03,-0.02,0, true);
        run("empty-brake", null, false, true, FlightPhase.BRAKE, 0.03,-0.02,0, false);
        run("player-brake", new Player(), false, true, FlightPhase.BRAKE, 0.03,-0.02,0, false);
        run("client", new Mob(), true, true, FlightPhase.BRAKE, 0.03,-0.02,0, false);
        run("airborne", new Mob(), false, false, FlightPhase.BRAKE, 0.03,-0.02,0, false);
        run("no-status", new Mob(), false, true, null, 0.03,-0.02,0, false);
        run("phase-not-brake", new Mob(), false, true, FlightPhase.TOUCHDOWN, 0.03,-0.02,0, false);
        run("speed-boundary", new Mob(), false, true, FlightPhase.BRAKE, 0.05,-0.02,0, true);
        run("speed-above", new Mob(), false, true, FlightPhase.BRAKE, 0.050000001,-0.02,0, false);
        run("vertical-clamp", new Mob(), false, true, FlightPhase.BRAKE, 0.03,0.02,0, true);
        System.out.println("FAILURES " + failures);
        if (failures != 0) System.exit(1);
    }
}
""",
}


class WheelLockStandaloneTest(unittest.TestCase):
    def test_wheel_lock_authority_and_controls(self):
        with tempfile.TemporaryDirectory(prefix="wheel-lock-standalone-") as temp:
            root = Path(temp)
            out = root / "classes"
            out.mkdir()
            empty = root / "empty-sourcepath"
            empty.mkdir()
            sources = []
            for name, content in STUBS.items():
                path = root / "stubs" / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
                sources.append(path)
            for name in ("AutopilotWheelLockAdapter.java", "MobPilotGate.java", "FlightPhase.java"):
                path = SOURCE / name
                source_bytes = path.read_bytes()
                print(f"source {name} sha256={hashlib.sha256(source_bytes).hexdigest()}", flush=True)
                snapshot = root / "production-source" / name
                snapshot.parent.mkdir(parents=True, exist_ok=True)
                snapshot.write_bytes(source_bytes)
                sources.append(snapshot)
            compiler = shutil.which("javac")
            java = shutil.which("java")
            self.assertIsNotNone(compiler, "javac is required")
            self.assertIsNotNone(java, "java is required")
            print(f"compiler={compiler}; runtime={java}; classpath={out}; sourcepath={empty}", flush=True)
            command = [compiler, "--release", "17", "-proc:none", "-classpath", str(out),
                       "-sourcepath", str(empty), "-d", str(out), *map(str, sources)]
            compile_result = subprocess.run(command, text=True, capture_output=True, check=False)
            print(compile_result.stdout + compile_result.stderr, end="", flush=True)
            self.assertEqual(compile_result.returncode, 0, "standalone compilation failed")
            # Optional: exercise Gradle-built classes with the same stand-ins. These
            # class files are separate evidence from the source compilation above.
            # Neither mode executes Minecraft/Forge or the real session manager.
            built = os.environ.get("WHEEL_LOCK_CLASSES_DIR")
            if built:
                built_dir = Path(built).resolve(strict=True)
                relative = Path("com/wwdebug/autopilot")
                for name in ("AutopilotWheelLockAdapter.class", "MobPilotGate.class", "FlightPhase.class"):
                    built_path = built_dir / relative / name
                    class_bytes = built_path.read_bytes()
                    print(f"built class {built_path} sha256={hashlib.sha256(class_bytes).hexdigest()}",
                          flush=True)
                    (out / relative / name).write_bytes(class_bytes)
                print("execution mode=Gradle-built classes with synthetic stand-ins", flush=True)
            else:
                print("execution mode=source-compiled classes with synthetic stand-ins", flush=True)
            result = subprocess.run([java, "-cp", str(out), "com.wwdebug.autopilot.WheelLockHarness"],
                                    text=True, capture_output=True, check=False)
            print(result.stdout + result.stderr, end="", flush=True)
            self.assertEqual(result.returncode, 0, "wheel-lock fixture failures above")


if __name__ == "__main__":
    unittest.main()
