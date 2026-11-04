package com.wwdebug.autopilot;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.lang.reflect.Method;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import net.minecraft.world.phys.AABB;
import net.minecraft.world.phys.Vec3;

/** Standalone checks against Minecraft geometry and the actual production predicate. */
public final class ProtectedCorridorGeometryCheck {
    private static final List<String> failures = new ArrayList<>();

    private static boolean blocked(AABB box, double width, Vec3 start, Vec3 end) throws Exception {
        try {
            // The implementation added by the fix is called directly once it exists.
            Method method = CombatWeaponManager.class.getDeclaredMethod("protectedCorridorHit",
                    AABB.class, double.class, Vec3.class, Vec3.class);
            method.setAccessible(true);
            return (boolean) method.invoke(null, box, width, start, end);
        } catch (NoSuchMethodException baseline) {
            // Baseline compatibility adapter: the original call uses precisely this production
            // distance method and width-based radius. This makes the same contract runnable red.
            Method legacy = CombatWeaponManager.class.getDeclaredMethod("distanceToSegment",
                    Vec3.class, Vec3.class, Vec3.class);
            legacy.setAccessible(true);
            double distance = (double) legacy.invoke(null, box.getCenter(), start, end);
            return distance <= Math.max(1.25, width * 0.5 + 0.8);
        }
    }

    private static void expect(String name, boolean expected, AABB box, double width,
                               Vec3 start, Vec3 end) throws Exception {
        boolean actual = blocked(box, width, start, end);
        if (actual != expected) failures.add(name + ": expected " + expected + ", got " + actual);
    }

    public static void main(String[] args) throws Exception {
        if (args.length == 1 && args[0].equals("--batch")) {
            try (BufferedReader reader = new BufferedReader(new InputStreamReader(System.in, StandardCharsets.UTF_8))) {
                String line;
                while ((line = reader.readLine()) != null) {
                    String[] fields = line.split(" ");
                    if (fields.length != 13) throw new IllegalArgumentException("expected 13 coordinates");
                    double[] v = new double[13];
                    for (int i = 0; i < v.length; i++) v[i] = Double.parseDouble(fields[i]);
                    boolean hit = blocked(new AABB(v[0], v[1], v[2], v[3], v[4], v[5]), v[6],
                            new Vec3(v[7], v[8], v[9]), new Vec3(v[10], v[11], v[12]));
                    System.out.println(hit ? "1" : "0");
                }
            }
            return;
        }
        AABB tall = new AABB(49.7, 100.0, -0.3, 50.3, 103.0, 0.3);
        Vec3 crossStart = new Vec3(0, 100.1, 0);
        Vec3 crossEnd = new Vec3(100, 100.1, 0);
        // Existing broad-phase selection must include this actual entity AABB.
        if (!new AABB(crossStart, crossEnd).inflate(3.0).intersects(tall)) {
            failures.add("tall candidate unexpectedly absent from the broad phase");
        }
        expect("tall body crossed near its feet", true, tall, 0.6, crossStart, crossEnd);
        expect("tangent to top face", true, tall, 0.6,
                new Vec3(0, 103, 0), new Vec3(100, 103, 0));
        expect("segment ends on top face", true, tall, 0.6,
                new Vec3(50, 104, 0), new Vec3(50, 103, 0));
        expect("segment starts on top face", true, tall, 0.6,
                new Vec3(50, 103, 0), new Vec3(50, 104, 0));
        expect("reverse crossing", true, tall, 0.6, crossEnd, crossStart);
        expect("corner touch", true, tall, 0.6,
                new Vec3(0, 103, 0.3), new Vec3(100, 103, 0.3));
        // Every literal is a fixed IEEE-754 binary64 value. Exact rational comparison
        // of those values confirms a very narrow common interval in all three axes.
        expect("rounding at a narrow corner", true,
                new AABB(3997533.3094341042, 56240011.30066386, -16250020.89039413,
                        3997533.309434105, 56240111.30066387, -16250020.890394127),
                1e-9,
                new Vec3(-6155439.892081633, 80998074.46776146, -35022419.16483397),
                new Vec3(45915291.89084762, -45976599.950397976, 61254060.25350538));
        expect("segment starts inside", true, tall, 0.6,
                new Vec3(50, 100.1, 0), new Vec3(50, 100.2, 0));
        expect("zero length inside", true, tall, 0.6,
                new Vec3(50, 100.1, 0), new Vec3(50, 100.1, 0));
        expect("zero length far outside", false, tall, 0.6,
                new Vec3(50, 110, 0), new Vec3(50, 110, 0));
        expect("legacy protection outside box", true, tall, 0.6,
                new Vec3(0, 101.5, 1.2), new Vec3(100, 101.5, 1.2));
        expect("far outside", false, tall, 0.6,
                new Vec3(0, 106, 0), new Vec3(100, 106, 0));
        expect("separated parallel segment", false, tall, 0.6,
                new Vec3(0, 100.1, 4), new Vec3(100, 100.1, 4));
        expect("non-finite start", true, tall, 0.6,
                new Vec3(Double.NaN, 100, 0), crossEnd);
        expect("non-finite width", true, tall, Double.NaN, crossStart, crossEnd);
        expect("invalid negative width", true, tall, -1,
                new Vec3(0, 110, 0), new Vec3(100, 110, 0));
        expect("non-finite bounds", true,
                new AABB(Double.NaN, 100, 0, 51, 103, 1), 0.6, crossStart, crossEnd);
        expect("overflowing segment difference", true, tall, 0.6,
                new Vec3(-Double.MAX_VALUE, 100.1, 0), new Vec3(Double.MAX_VALUE, 100.1, 0));
        expect("finite segment with non-finite legacy intermediate", true,
                new AABB(1e307, 100, -0.3, 1.1e307, 103, 0.3), 0.6,
                new Vec3(0, 0, 0), new Vec3(1e308, 0, 0));
        if (!failures.isEmpty()) throw new AssertionError(String.join("\n", failures));
        System.out.println("PASS: protected corridor geometry checks");
    }
}
