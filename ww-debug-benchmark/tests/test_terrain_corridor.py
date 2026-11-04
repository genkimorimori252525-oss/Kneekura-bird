"""Exercise the real planner against a deterministic stand-in for world ray clips.

The Java doubles replace Minecraft types, not the planner. This is a cheap geometry
precheck; it does not establish Minecraft/Forge collision or aircraft behaviour.
"""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
PLANNER = Path(os.environ.get("TERRAIN_PLANNER_SOURCE", ROOT / "src/main/java/com/wwdebug/autopilot/TerrainAvoidancePlanner.java"))
JAVA_HOME = os.environ.get("JAVA_HOME")
JAVAC = str(Path(JAVA_HOME) / "bin/javac") if JAVA_HOME else shutil.which("javac")
JAVA = str(Path(JAVA_HOME) / "bin/java") if JAVA_HOME else shutil.which("java")

DOUBLES = {
    "net/minecraft/util/Mth.java": """
package net.minecraft.util;
public class Mth {
    public static double clamp(double n, double min, double max) {
        return Math.max(min, Math.min(max, n));
    }
}
""",
    "net/minecraft/world/phys/Vec3.java": """
package net.minecraft.world.phys;
public class Vec3 {
    public static final Vec3 ZERO = new Vec3(0, 0, 0);
    public final double x, y, z;
    public Vec3(double x, double y, double z) { this.x=x; this.y=y; this.z=z; }
    public Vec3 add(double x, double y, double z) { return new Vec3(this.x+x, this.y+y, this.z+z); }
    public Vec3 add(Vec3 v) { return add(v.x,v.y,v.z); }
    public Vec3 scale(double v) { return new Vec3(x*v,y*v,z*v); }
    public double lengthSqr() { return x*x+y*y+z*z; }
    public Vec3 normalize() { double n=Math.sqrt(lengthSqr()); return n<1e-4 ? ZERO : scale(1/n); }
    public double dot(Vec3 v) { return x*v.x+y*v.y+z*v.z; }
    public double distanceTo(Vec3 v) {
        return Math.sqrt((x-v.x)*(x-v.x)+(y-v.y)*(y-v.y)+(z-v.z)*(z-v.z));
    }
}
""",
    "net/minecraft/world/phys/HitResult.java": """
package net.minecraft.world.phys;
public class HitResult { public enum Type { MISS, BLOCK } }
""",
    "net/minecraft/world/phys/BlockHitResult.java": """
package net.minecraft.world.phys;
public class BlockHitResult extends HitResult {
    private final Type type; private final Vec3 location;
    public BlockHitResult(Type type, Vec3 location) { this.type=type; this.location=location; }
    public Type getType() { return type; }
    public Vec3 getLocation() { return location; }
}
""",
    "net/minecraft/world/level/ClipContext.java": """
package net.minecraft.world.level;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.phys.Vec3;
public class ClipContext {
    public enum Block { COLLIDER } public enum Fluid { NONE }
    public final Vec3 from, to;
    public ClipContext(Vec3 from, Vec3 to, Block block, Fluid fluid, Entity entity) {
        this.from=from; this.to=to;
    }
}
""",
    "net/minecraft/world/level/Level.java": """
package net.minecraft.world.level;
import net.minecraft.world.phys.BlockHitResult;
import net.minecraft.world.phys.HitResult;
import net.minecraft.world.phys.Vec3;
public class Level {
    private final double fraction; private final int selectedRay; private int calls;
    public Level(double fraction, int selectedRay) { this.fraction=fraction; this.selectedRay=selectedRay; }
    public long getGameTime() { return 123; }
    public BlockHitResult clip(ClipContext ray) {
        int rayIndex=calls++;
        if (fraction < 0 || (selectedRay >= 0 && rayIndex != selectedRay)) {
            return new BlockHitResult(HitResult.Type.MISS, ray.to);
        }
        Vec3 p=ray.from.add((ray.to.x-ray.from.x)*fraction, (ray.to.y-ray.from.y)*fraction,
                            (ray.to.z-ray.from.z)*fraction);
        return new BlockHitResult(HitResult.Type.BLOCK, p);
    }
}
""",
    "net/minecraft/world/entity/Entity.java": """
package net.minecraft.world.entity;
import java.util.UUID;
import net.minecraft.world.level.Level;
public class Entity {
    private final Level level; private final UUID uuid=UUID.randomUUID();
    public Entity(Level level) { this.level=level; }
    public Level level() { return level; }
    public UUID getUUID() { return uuid; }
    public double getBbWidth() { return 4.0; }
    public double getBbHeight() { return 2.0; }
}
""",
    "com/wwdebug/autopilot/FlightPhase.java": """
package com.wwdebug.autopilot;
public enum FlightPhase {
    ROTATE, CLIMB, CRUISE_OUTBOUND, STALL_ENTRY, STALL_RECOVERY,
    FINAL, FLARE, TOUCHDOWN, BRAKE, PARKED, ABORTED;
    public boolean isAirborneMissionPhase() { return true; }
}
""",
    "com/wwdebug/autopilot/FlightSnapshot.java": """
package com.wwdebug.autopilot;
import net.minecraft.world.phys.Vec3;
public record FlightSnapshot(Vec3 position, Vec3 horizontalForward, double horizontalSpeedBps,
                             double altitudeAboveGround, boolean onGround) { }
""",
    "com/wwdebug/autopilot/FlightControlOutput.java": """
package com.wwdebug.autopilot;
import net.minecraft.world.phys.Vec3;
public record FlightControlOutput(Vec3 desiredDirection, double targetAltitude) { }
""",
    "com/wwdebug/autopilot/TerrainCorridorCheck.java": """
package com.wwdebug.autopilot;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.level.Level;
import net.minecraft.world.phys.Vec3;
public final class TerrainCorridorCheck {
    public static void main(String[] args) {
        double rise=Double.parseDouble(args[0]);
        double fraction=Double.parseDouble(args[1]);
        int ray=Integer.parseInt(args[2]);
        double dx=Double.parseDouble(args[3]), dz=Double.parseDouble(args[4]);
        double speed=Double.parseDouble(args[5]);
        Vec3 origin=new Vec3(30.0,100.0,-40.0);
        Vec3 direction=new Vec3(dx,0,dz).normalize();
        var snapshot=new FlightSnapshot(origin,direction,speed,100.0,false);
        var output=new FlightControlOutput(direction,origin.y+rise);
        var entity=new Entity(new Level(fraction,ray));
        var result=TerrainAvoidancePlanner.plan(entity,FlightPhase.CRUISE_OUTBOUND,
                                                snapshot,output,new TerrainAvoidancePlanner.State());
        System.out.printf(java.util.Locale.ROOT, "%s %.12f %.12f %.12f%n",
                          result.active(),result.lookAheadBlocks(),result.directClearanceBlocks(),
                          result.selectedClearanceBlocks());
    }
}
""",
}


class TerrainCorridorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not JAVAC or not JAVA:
            raise RuntimeError("JDK 17 is required for terrain corridor checks")
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        for name, source in DOUBLES.items():
            path = cls.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(source, encoding="utf-8")
        command = [JAVAC, "--release", "17", "-d", str(cls.root), str(PLANNER)]
        command.extend(str(cls.root / name) for name in DOUBLES)
        subprocess.run(command, check=True, capture_output=True, text=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def check_corridor(self, rise, fraction, selected_ray=-1, direction=(1, 0),
                       speed=100.0 / 4.2):
        run = subprocess.run([JAVA, "-cp", str(self.root),
                              "com.wwdebug.autopilot.TerrainCorridorCheck", str(rise),
                              str(fraction), str(selected_ray), *map(str, direction), str(speed)],
                             check=True, capture_output=True, text=True)
        active, lookahead, clearance, selected = run.stdout.split()
        return active == "true", float(lookahead), float(clearance), float(selected)

    def test_sloped_hit_inside_horizontal_corridor_activates_avoidance(self):
        for rise in (100, -100):
            with self.subTest(rise=rise):
                active, lookahead, clearance, _ = self.check_corridor(rise, 0.8)
                self.assertTrue(active)
                self.assertAlmostEqual(lookahead, 100.0)
                self.assertAlmostEqual(clearance, 80.0)

    def test_any_one_of_five_offset_rays_can_detect_sloped_obstacle(self):
        for ray in range(5):
            with self.subTest(ray=ray):
                active, _, clearance, _ = self.check_corridor(100, 0.8, ray, (1, 1))
                self.assertTrue(active)
                self.assertAlmostEqual(clearance, 80.0)

    def test_previously_detected_flat_and_near_sloped_hits_still_activate(self):
        for rise, fraction in ((0, 0.8), (100, 0.5), (-100, 0.5)):
            with self.subTest(rise=rise):
                active, _, clearance, _ = self.check_corridor(rise, fraction)
                self.assertTrue(active)
                self.assertAlmostEqual(clearance, fraction * 100.0)

    def test_floating_point_boundary_keeps_the_old_risk_detection(self):
        # Independently found JDK 17 case: the old sqrt rounds just below 92,
        # while hypot can round to 92 exactly; the risk threshold is 92.
        active, _, _, _ = self.check_corridor(
            0, 0.92, direction=(0.999999999758, 2.1999999998225333e-05))
        self.assertTrue(active)

    def test_miss_and_hit_beyond_horizontal_risk_threshold_stay_clear(self):
        for fraction in (-1, 0.95):
            with self.subTest(fraction=fraction):
                active, _, clearance, _ = self.check_corridor(100, fraction)
                self.assertFalse(active)
                self.assertAlmostEqual(clearance, 100.0 if fraction < 0 else 95.0)

    def test_steep_detour_candidate_clearance_uses_horizontal_distance(self):
        # The direct ray is horizontal; the planner's candidate rays climb.
        active, _, direct, selected = self.check_corridor(0, 0.8)
        self.assertTrue(active)
        self.assertAlmostEqual(direct, 80.0)
        self.assertAlmostEqual(selected, 80.0)

    def test_sloped_detection_across_clamped_lookahead_limits(self):
        for speed, rise, fraction, expected_lookahead, expected_clearance in (
                (1.0, 40.0, 0.8, 64.0, 51.2),
                (100.0, 100.0, 0.85, 190.0, 161.5)):
            with self.subTest(speed=speed):
                active, lookahead, clearance, _ = self.check_corridor(rise, fraction, speed=speed)
                self.assertTrue(active)
                self.assertAlmostEqual(lookahead, expected_lookahead)
                self.assertAlmostEqual(clearance, expected_clearance)


if __name__ == "__main__":
    unittest.main()
