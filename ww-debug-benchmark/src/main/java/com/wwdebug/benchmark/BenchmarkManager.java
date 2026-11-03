package com.wwdebug.benchmark;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import net.minecraft.commands.CommandSourceStack;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.network.chat.Component;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.util.Mth;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.entity.decoration.ArmorStand;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.level.ChunkPos;
import net.minecraft.world.level.storage.LevelResource;
import net.minecraft.world.phys.Vec3;
import net.minecraftforge.fml.ModList;

import javax.annotation.Nullable;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.Deque;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

public final class BenchmarkManager {
    private static final int MAX_CONCURRENT = 6;
    private static final Gson GSON = new GsonBuilder().setPrettyPrinting().create();
    private static final DateTimeFormatter FILE_TIME = DateTimeFormatter.ofPattern("yyyyMMdd-HHmmss")
            .withLocale(Locale.ROOT)
            .withZone(ZoneOffset.UTC);
    private static final Map<MinecraftServer, BenchmarkSession> SESSIONS = new ConcurrentHashMap<>();
    private static final Map<UUID, ControlInput> CONTROLS = new ConcurrentHashMap<>();
    private static final Set<UUID> CONTROL_HEARTBEATS = ConcurrentHashMap.newKeySet();

    private BenchmarkManager() {
    }

    public static void tick(MinecraftServer server) {
        BenchmarkSession session = SESSIONS.get(server);
        if (session == null) {
            return;
        }
        try {
            session.tick();
            if (session.complete()) {
                session.finish();
                SESSIONS.remove(server, session);
            }
        } catch (Exception exception) {
            WWDebugBenchmarkMod.LOGGER.error("Aircraft benchmark failed", exception);
            session.abort();
            SESSIONS.remove(server, session);
        }
    }

    public static void applyControl(Entity vehicle) {
        if (vehicle.level().isClientSide) {
            return;
        }
        ControlInput input = CONTROLS.get(vehicle.getUUID());
        if (input != null) {
            CONTROL_HEARTBEATS.add(vehicle.getUUID());
            ReflectiveAircraft.applyControl(vehicle, input.x(), input.y(), input.z(), input.engineTarget());
        }
    }

    public static int start(CommandSourceStack source, BenchmarkCategory category, boolean includeVariants) {
        MinecraftServer server = source.getServer();
        if (SESSIONS.containsKey(server)) {
            source.sendFailure(Component.literal("A benchmark is already running. Use /wwdebug benchmark status or stop."));
            return 0;
        }

        List<Candidate> candidates = discover(source.getLevel(), category, includeVariants);
        if (candidates.isEmpty()) {
            source.sendFailure(Component.literal("No compatible aircraft were found for category " + category.id() + "."));
            return 0;
        }

        BenchmarkSession session = new BenchmarkSession(source, category, includeVariants, candidates);
        SESSIONS.put(server, session);
        source.sendSuccess(() -> Component.literal(
                "Benchmark started for " + candidates.size() + " aircraft (max " + MAX_CONCURRENT
                        + " simultaneously). Variants=" + includeVariants + "."
        ), false);
        return candidates.size();
    }

    public static int list(CommandSourceStack source, boolean includeVariants) {
        List<Candidate> candidates = discover(source.getLevel(), BenchmarkCategory.ALL, includeVariants);
        source.sendSuccess(() -> Component.literal(
                "Compatible aircraft: " + candidates.size() + " (variants=" + includeVariants + ")"
        ), false);
        int limit = Math.min(40, candidates.size());
        for (int index = 0; index < limit; index++) {
            Candidate candidate = candidates.get(index);
            source.sendSuccess(() -> Component.literal(
                    "- [" + candidate.metadata().category().id() + "] " + candidate.id()
                            + " doctrine=" + candidate.metadata().doctrine()
                            + " faction=" + candidate.metadata().faction()
            ), false);
        }
        if (limit < candidates.size()) {
            source.sendSuccess(() -> Component.literal("...and " + (candidates.size() - limit) + " more."), false);
        }
        return candidates.size();
    }

    public static int status(CommandSourceStack source) {
        BenchmarkSession session = SESSIONS.get(source.getServer());
        if (session == null) {
            source.sendSuccess(() -> Component.literal("No benchmark is running."), false);
            return 0;
        }
        source.sendSuccess(() -> Component.literal(session.status()), false);
        return session.finishedCount();
    }

    public static int stop(CommandSourceStack source) {
        MinecraftServer server = source.getServer();
        BenchmarkSession session = SESSIONS.get(server);
        if (session == null) {
            source.sendFailure(Component.literal("No benchmark is running."));
            return 0;
        }
        if (session.surrenderOccupiedTests()) {
            source.sendFailure(Component.literal(
                    "Benchmark stop refused: an aircraft has been taken over by a player."));
            return 0;
        }
        if (!SESSIONS.remove(server, session)) {
            source.sendFailure(Component.literal("Benchmark session changed before it could be stopped."));
            return 0;
        }
        session.abort();
        source.sendSuccess(() -> Component.literal("Benchmark stopped and test entities removed."), false);
        return 1;
    }

    public static void stopSilently(MinecraftServer server) {
        BenchmarkSession session = SESSIONS.remove(server);
        if (session != null) {
            session.abort();
        }
    }

    private static List<Candidate> discover(ServerLevel level, BenchmarkCategory category, boolean includeVariants) {
        List<Candidate> candidates = new ArrayList<>();
        Set<String> variantGroups = new HashSet<>();

        for (EntityType<?> type : BuiltInRegistries.ENTITY_TYPE) {
            Entity entity = null;
            try {
                entity = type.create(level);
                if (entity == null || !ReflectiveAircraft.isAirplane(entity) || !ReflectiveAircraft.isControllable(entity)) {
                    continue;
                }

                ResourceLocation id = BuiltInRegistries.ENTITY_TYPE.getKey(type);
                AircraftMetadata metadata = AircraftMetadataResolver.resolve(level.getServer().getResourceManager(), id);
                if (!category.matches(metadata)) {
                    continue;
                }
                if (!includeVariants && !variantGroups.add(metadata.variantGroup())) {
                    continue;
                }
                candidates.add(new Candidate(type, id, metadata));
            } catch (Throwable throwable) {
                WWDebugBenchmarkMod.LOGGER.debug("Could not inspect aircraft type", throwable);
            } finally {
                if (entity != null) {
                    entity.discard();
                }
            }
        }

        candidates.sort(Comparator
                .comparing((Candidate candidate) -> candidate.metadata().category().ordinal())
                .thenComparing(candidate -> candidate.metadata().variantGroup())
                .thenComparing(candidate -> candidate.id().toString()));
        return candidates;
    }

    private record Candidate(EntityType<?> type, ResourceLocation id, AircraftMetadata metadata) {
    }

    private record ControlInput(float x, float y, float z, float engineTarget) {
        private ControlInput {
            x = Mth.clamp(x, -1.0f, 1.0f);
            y = Mth.clamp(y, -1.0f, 1.0f);
            z = Mth.clamp(z, -1.0f, 1.0f);
            engineTarget = Mth.clamp(engineTarget, 0.0f, 1.0f);
        }
    }

    private enum Phase {
        PREPARE(220),
        STRAIGHT_ACCELERATION(600),
        TURN_WARMUP(160),
        SUSTAINED_TURN(240),
        CLIMB_WARMUP(160),
        CLIMB(220),
        STALL_WARMUP(160),
        STALL_DECELERATION(320),
        BRAKE_WARMUP(160),
        BRAKE(600),
        COMPLETE(0);

        private final int maximumTicks;

        Phase(int maximumTicks) {
            this.maximumTicks = maximumTicks;
        }
    }

    private static final class BenchmarkSession {
        private final CommandSourceStack source;
        private final MinecraftServer server;
        private final ServerLevel level;
        private final BenchmarkCategory category;
        private final boolean includeVariants;
        private final Vec3 origin;
        private final Deque<Candidate> pending;
        private final List<AircraftTest> active = new ArrayList<>();
        private final List<Map<String, Object>> results = new ArrayList<>();
        private final int total;
        private int elapsedTicks;

        private BenchmarkSession(CommandSourceStack source, BenchmarkCategory category,
                                 boolean includeVariants, List<Candidate> candidates) {
            this.source = source;
            this.server = source.getServer();
            this.level = source.getLevel();
            this.category = category;
            this.includeVariants = includeVariants;
            this.origin = source.getPosition();
            this.pending = new ArrayDeque<>(candidates);
            this.total = candidates.size();
            fillBatch();
        }

        private void tick() {
            elapsedTicks++;
            for (AircraftTest test : new ArrayList<>(active)) {
                test.tick();
                if (test.finished() && !test.surrenderIfOccupied()) {
                    Map<String, Object> result = test.result();
                    if (test.surrenderIfOccupied()) {
                        continue;
                    }
                    results.add(result);
                    test.cleanup();
                    active.remove(test);
                }
            }
            fillBatch();
        }

        private boolean surrenderOccupiedTests() {
            boolean surrendered = false;
            for (AircraftTest test : active) {
                if (test.surrenderIfOccupied()) {
                    surrendered = true;
                }
            }
            return surrendered;
        }

        private void fillBatch() {
            while (active.size() < MAX_CONCURRENT && !pending.isEmpty()) {
                if (surrenderOccupiedTests()) {
                    return;
                }
                Candidate candidate = pending.removeFirst();
                Vec3 anchor = anchor(active.size());
                AircraftTest test = AircraftTest.spawn(level, candidate, anchor);
                if (test == null) {
                    results.add(failedSpawn(candidate));
                } else {
                    active.add(test);
                }
            }
        }

        private Vec3 anchor(int slot) {
            int column = slot % 3;
            int row = slot / 3;
            double safeY = Mth.clamp(origin.y + 105.0, level.getMinBuildHeight() + 80.0, level.getMaxBuildHeight() - 50.0);
            return new Vec3(
                    origin.x + (column - 1) * 150.0,
                    safeY + row * 34.0,
                    origin.z + row * 170.0
            );
        }

        private boolean complete() {
            return pending.isEmpty() && active.isEmpty() && results.size() >= total;
        }

        private int finishedCount() {
            return results.size();
        }

        private String status() {
            Map<Phase, Integer> phases = new LinkedHashMap<>();
            for (AircraftTest test : active) {
                phases.merge(test.phase(), 1, Integer::sum);
            }
            return "Aircraft benchmark " + finishedCount() + "/" + total
                    + " complete; active=" + active.size()
                    + "; queued=" + pending.size()
                    + "; elapsed=" + String.format(Locale.ROOT, "%.1fs", elapsedTicks / 20.0)
                    + "; phases=" + phases;
        }

        private void finish() {
            Path root = server.getWorldPath(LevelResource.ROOT).resolve("wwdebug").resolve("benchmarks");
            String runId = FILE_TIME.format(Instant.now()) + "-" + category.id()
                    + (includeVariants ? "-variants" : "-representatives");
            Path runDirectory = root.resolve(runId);
            Path latestFile = root.resolve("latest.json");
            Path latestSuccessfulFile = root.resolve("latest_successful.json");

            try {
                Files.createDirectories(runDirectory);
                List<Map<String, Object>> previous = readPrevious(latestSuccessfulFile);
                Files.writeString(runDirectory.resolve("benchmark.json"), GSON.toJson(results), StandardCharsets.UTF_8);
                Files.writeString(runDirectory.resolve("benchmark.csv"), buildCsv(results), StandardCharsets.UTF_8);
                Files.writeString(runDirectory.resolve("flight_profiles.json"), GSON.toJson(buildProfiles(results)), StandardCharsets.UTF_8);
                Files.writeString(runDirectory.resolve("comparison.csv"), buildComparison(previous, results), StandardCharsets.UTF_8);
                Files.writeString(runDirectory.resolve("run_metadata.json"), GSON.toJson(runMetadata(runId)), StandardCharsets.UTF_8);
                Files.writeString(latestFile, GSON.toJson(results), StandardCharsets.UTF_8);
                boolean fullyValid = results.stream().allMatch(row -> "ok".equals(row.get("status")));
                if (fullyValid) {
                    Files.writeString(latestSuccessfulFile, GSON.toJson(results), StandardCharsets.UTF_8);
                }

                source.sendSuccess(() -> Component.literal(
                        "Benchmark complete: " + results.size() + "/" + total
                                + ". Results: " + runDirectory.toAbsolutePath()
                ), false);
            } catch (IOException exception) {
                WWDebugBenchmarkMod.LOGGER.error("Could not write benchmark output", exception);
                source.sendFailure(Component.literal("Benchmark finished, but output failed: " + exception.getMessage()));
            }
        }

        private Map<String, Object> runMetadata(String runId) {
            Map<String, Object> metadata = new LinkedHashMap<>();
            metadata.put("run_id", runId);
            metadata.put("timestamp_utc", Instant.now().toString());
            metadata.put("category", category.id());
            metadata.put("include_variants", includeVariants);
            metadata.put("aircraft_count", total);
            metadata.put("elapsed_ticks", elapsedTicks);
            metadata.put("dimension", level.dimension().location().toString());
            metadata.put("raining", level.isRaining());
            metadata.put("thundering", level.isThundering());
            metadata.put("minecraft_version", modVersion("minecraft"));
            metadata.put("forge_version", modVersion("forge"));
            metadata.put("immersive_aircraft_version", modVersion("immersive_aircraft"));
            metadata.put("warfare_wings_version", modVersion("warfare_wings"));
            metadata.put("benchmark_mod_version", modVersion(WWDebugBenchmarkMod.MOD_ID));
            return metadata;
        }

        private String modVersion(String modId) {
            return ModList.get().getModContainerById(modId)
                    .map(container -> container.getModInfo().getVersion().toString())
                    .orElse("unknown");
        }

        private void abort() {
            pending.clear();
            for (AircraftTest test : active) {
                test.cleanup();
            }
            active.clear();
        }

        private Map<String, Object> failedSpawn(Candidate candidate) {
            Map<String, Object> result = baseMetadata(candidate);
            result.put("status", "failed");
            result.put("error", "Could not spawn aircraft or dummy pilot");
            return result;
        }
    }

    private static final class AircraftTest {
        private final Candidate candidate;
        private final Entity aircraft;
        private final ArmorStand pilot;
        private final Vec3 anchor;
        private final Map<String, Double> effectiveStats;
        private final List<Double> accelerationSpeeds = new ArrayList<>();
        private final Set<Long> ownedForcedChunks = new HashSet<>();
        private Phase phase = Phase.PREPARE;
        private int phaseTick;
        private int stablePrepareTicks;
        private boolean finished;
        private boolean surrenderedToPlayer;
        private String error = "";
        private double accelerationInitialSpeed = Double.NaN;
        private double accelerationInitialEnginePower = Double.NaN;
        private double topSpeed;
        private double timeTo50 = Double.NaN;
        private double timeTo90 = Double.NaN;
        private double timeTo95 = Double.NaN;
        private float previousYaw;
        private float previousPitch;
        private double turnDegrees;
        private double turnSpeedSum;
        private double turnVerticalSpeedSum;
        private double turnStartY;
        private double turnEndY;
        private int turnSamples;
        private double climbRateSum;
        private double climbSpeedSum;
        private int climbSamples;
        private double pitchDegrees;
        private int pitchSamples;
        private int fallingTicks;
        private double stallProxySpeed = Double.NaN;
        private double brakeInitialSpeed;
        private double brakeDistance;
        private double brakeTime50 = Double.NaN;
        private double brakeTime10 = Double.NaN;
        private boolean brakeReachedTenPercent;
        private int brakeLowSpeedTicks;

        private AircraftTest(Candidate candidate, Entity aircraft, ArmorStand pilot, Vec3 anchor) {
            this.candidate = candidate;
            this.aircraft = aircraft;
            this.pilot = pilot;
            this.anchor = anchor;
            this.effectiveStats = ReflectiveAircraft.effectiveStats(aircraft);
            keepChunksLoaded();
            CONTROLS.put(aircraft.getUUID(), new ControlInput(0, 0, 0, 0));
        }

        @Nullable
        private static AircraftTest spawn(ServerLevel level, Candidate candidate, Vec3 anchor) {
            Entity aircraft = null;
            ArmorStand pilot = null;
            try {
                aircraft = candidate.type().create(level);
                if (aircraft == null || !ReflectiveAircraft.isAirplane(aircraft)) {
                    return null;
                }
                aircraft.moveTo(anchor.x, anchor.y, anchor.z, 0.0f, 0.0f);
                aircraft.setInvulnerable(true);
                aircraft.setCustomName(Component.literal("BENCH " + candidate.id()));
                aircraft.setCustomNameVisible(true);

                pilot = EntityType.ARMOR_STAND.create(level);
                if (pilot == null) {
                    aircraft.discard();
                    return null;
                }
                pilot.moveTo(anchor.x, anchor.y, anchor.z, 0.0f, 0.0f);
                pilot.setInvisible(true);
                pilot.setInvulnerable(true);
                pilot.setNoGravity(true);
                pilot.setCustomName(Component.literal("WW benchmark pilot"));

                level.addFreshEntity(aircraft);
                level.addFreshEntity(pilot);
                if (!pilot.startRiding(aircraft, true)) {
                    pilot.discard();
                    aircraft.discard();
                    return null;
                }
                ReflectiveAircraft.fillFuel(aircraft);
                return new AircraftTest(candidate, aircraft, pilot, anchor);
            } catch (Throwable throwable) {
                if (pilot != null) {
                    pilot.discard();
                }
                if (aircraft != null) {
                    aircraft.discard();
                }
                WWDebugBenchmarkMod.LOGGER.warn("Could not spawn benchmark aircraft {}", candidate.id(), throwable);
                return null;
            }
        }

        private boolean surrenderIfOccupied() {
            if (!surrenderedToPlayer && aircraft.getSelfAndPassengers().anyMatch(Player.class::isInstance)) {
                surrenderedToPlayer = true;
            }
            if (surrenderedToPlayer) {
                UUID aircraftId = aircraft.getUUID();
                CONTROLS.remove(aircraftId);
                CONTROL_HEARTBEATS.remove(aircraftId);
            }
            return surrenderedToPlayer;
        }

        private void tick() {
            if (surrenderIfOccupied() || finished) {
                return;
            }
            keepChunksLoaded();
            if (aircraft.isRemoved() || pilot.isRemoved() || !pilot.isPassengerOfSameVehicle(aircraft)) {
                fail("Aircraft or benchmark pilot was removed");
                return;
            }
            if (phase == Phase.PREPARE) {
                boolean heartbeat = CONTROL_HEARTBEATS.contains(aircraft.getUUID());
                double speed = aircraft.getDeltaMovement().length() * 20.0;
                double enginePower = ReflectiveAircraft.enginePower(aircraft);
                boolean engineSettled = !Double.isFinite(enginePower) || enginePower <= 0.02;
                if (heartbeat && speed <= 0.25 && engineSettled) {
                    stablePrepareTicks++;
                } else {
                    stablePrepareTicks = 0;
                }
                if (phaseTick >= 180 && !heartbeat) {
                    fail("VehicleEntity.tickPilot control hook was not observed");
                    return;
                }
                if (phaseTick >= phase.maximumTicks && stablePrepareTicks < 20) {
                    fail("Aircraft did not settle before acceleration sampling");
                    return;
                }
            }

            ReflectiveAircraft.fillFuel(aircraft);
            sample();
            phaseTick++;
            if (shouldAdvance()) {
                finishPhase();
                advancePhase();
            }
            applyControl();
        }

        private void sample() {
            Vec3 velocity = aircraft.getDeltaMovement();
            double horizontalSpeed = velocity.horizontalDistance() * 20.0;
            double totalSpeed = velocity.length() * 20.0;

            switch (phase) {
                case STRAIGHT_ACCELERATION -> {
                    accelerationSpeeds.add(horizontalSpeed);
                    topSpeed = Math.max(topSpeed, horizontalSpeed);
                }
                case SUSTAINED_TURN -> {
                    if (phaseTick >= 60) {
                        turnDegrees += Math.abs(Mth.wrapDegrees(aircraft.getYRot() - previousYaw));
                        turnSpeedSum += horizontalSpeed;
                        turnVerticalSpeedSum += velocity.y * 20.0;
                        turnSamples++;
                    }
                    previousYaw = aircraft.getYRot();
                }
                case CLIMB -> {
                    if (phaseTick >= 50) {
                        climbRateSum += velocity.y * 20.0;
                        climbSpeedSum += totalSpeed;
                        climbSamples++;
                    }
                    if (phaseTick < 50) {
                        pitchDegrees += Math.abs(Mth.wrapDegrees(aircraft.getXRot() - previousPitch));
                        pitchSamples++;
                    }
                    previousPitch = aircraft.getXRot();
                }
                case STALL_DECELERATION -> {
                    if (velocity.y * 20.0 < -1.0) {
                        fallingTicks++;
                        if (fallingTicks >= 8 && Double.isNaN(stallProxySpeed)) {
                            stallProxySpeed = horizontalSpeed;
                        }
                    } else {
                        fallingTicks = 0;
                    }
                }
                case BRAKE -> {
                    if (phaseTick == 0) {
                        brakeInitialSpeed = horizontalSpeed;
                    }
                    brakeDistance += velocity.horizontalDistance();
                    if (brakeInitialSpeed > 0.0) {
                        if (Double.isNaN(brakeTime50) && horizontalSpeed <= brakeInitialSpeed * 0.5) {
                            brakeTime50 = phaseTick / 20.0;
                        }
                        if (Double.isNaN(brakeTime10) && horizontalSpeed <= brakeInitialSpeed * 0.1) {
                            brakeTime10 = phaseTick / 20.0;
                            brakeReachedTenPercent = true;
                        }
                        if (horizontalSpeed <= brakeInitialSpeed * 0.1) {
                            brakeLowSpeedTicks++;
                        } else {
                            brakeLowSpeedTicks = 0;
                        }
                    }
                }
                default -> {
                }
            }
        }

        private boolean shouldAdvance() {
            if (phase == Phase.PREPARE && stablePrepareTicks >= 20) {
                return true;
            }
            if (phase == Phase.STRAIGHT_ACCELERATION && phaseTick >= 240 && accelerationSpeeds.size() >= 160) {
                double oldAverage = averageTail(accelerationSpeeds, 160, 80);
                double newAverage = averageTail(accelerationSpeeds, 80, 0);
                double denominator = Math.max(0.01, newAverage);
                if (Math.abs(newAverage - oldAverage) / denominator < 0.0035) {
                    return true;
                }
            }
            if (phase == Phase.STALL_DECELERATION
                    && ((!Double.isNaN(stallProxySpeed) && phaseTick >= 80) || aircraft.getDeltaMovement().horizontalDistance() < 0.01)) {
                return true;
            }
            if (phase == Phase.BRAKE && brakeLowSpeedTicks >= 20) {
                return true;
            }
            return phaseTick >= phase.maximumTicks;
        }

        private double averageTail(List<Double> values, int fromEnd, int toEnd) {
            int start = Math.max(0, values.size() - fromEnd);
            int end = Math.max(start, values.size() - toEnd);
            return values.subList(start, end).stream().mapToDouble(Double::doubleValue).average().orElse(0.0);
        }

        private void finishPhase() {
            if (phase == Phase.STRAIGHT_ACCELERATION && !accelerationSpeeds.isEmpty()) {
                double steadySpeed = averageTail(accelerationSpeeds, Math.min(80, accelerationSpeeds.size()), 0);
                findAccelerationTime(steadySpeed * 0.50, value -> timeTo50 = value);
                findAccelerationTime(steadySpeed * 0.90, value -> timeTo90 = value);
                findAccelerationTime(steadySpeed * 0.95, value -> timeTo95 = value);
            }
        }

        private void findAccelerationTime(double threshold, java.util.function.DoubleConsumer setter) {
            for (int index = 0; index < accelerationSpeeds.size(); index++) {
                if (accelerationSpeeds.get(index) >= threshold) {
                    setter.accept(index / 20.0);
                    return;
                }
            }
        }

        private void advancePhase() {
            phaseTick = 0;
            phase = switch (phase) {
                case PREPARE -> {
                    accelerationInitialSpeed = aircraft.getDeltaMovement().horizontalDistance() * 20.0;
                    accelerationInitialEnginePower = ReflectiveAircraft.enginePower(aircraft);
                    resetFlight();
                    yield Phase.STRAIGHT_ACCELERATION;
                }
                case STRAIGHT_ACCELERATION -> {
                    resetFlight();
                    yield Phase.TURN_WARMUP;
                }
                case TURN_WARMUP -> {
                    previousYaw = aircraft.getYRot();
                    turnStartY = aircraft.getY();
                    yield Phase.SUSTAINED_TURN;
                }
                case SUSTAINED_TURN -> {
                    turnEndY = aircraft.getY();
                    resetFlight();
                    yield Phase.CLIMB_WARMUP;
                }
                case CLIMB_WARMUP -> {
                    previousPitch = aircraft.getXRot();
                    yield Phase.CLIMB;
                }
                case CLIMB -> {
                    resetFlight();
                    yield Phase.STALL_WARMUP;
                }
                case STALL_WARMUP -> Phase.STALL_DECELERATION;
                case STALL_DECELERATION -> {
                    resetFlight();
                    yield Phase.BRAKE_WARMUP;
                }
                case BRAKE_WARMUP -> Phase.BRAKE;
                case BRAKE -> Phase.COMPLETE;
                case COMPLETE -> Phase.COMPLETE;
            };

            if (phase == Phase.COMPLETE) {
                finished = true;
                CONTROLS.remove(aircraft.getUUID());
            }
        }

        private void applyControl() {
            if (finished) {
                return;
            }
            double yawSpeed = Math.max(0.1, stat("yawSpeed", 1.0));
            double pitchSpeed = Math.max(0.1, stat("pitchSpeed", 1.0));
            float yawCorrection = Mth.clamp((float) (Mth.wrapDegrees(-aircraft.getYRot()) / yawSpeed), -1.0f, 1.0f);
            float levelPitch = Mth.clamp((float) (Mth.wrapDegrees(-aircraft.getXRot()) / pitchSpeed), -1.0f, 1.0f);
            float climbPitch = Mth.clamp((float) (Mth.wrapDegrees(-15.0f - aircraft.getXRot()) / pitchSpeed), -1.0f, 1.0f);

            ControlInput control = switch (phase) {
                case PREPARE -> new ControlInput(0, 0, 0, 0);
                case STRAIGHT_ACCELERATION, TURN_WARMUP, CLIMB_WARMUP, STALL_WARMUP, BRAKE_WARMUP ->
                        new ControlInput(yawCorrection, 0, levelPitch, 1);
                case SUSTAINED_TURN -> new ControlInput(1, 0, levelPitch, 1);
                case CLIMB -> new ControlInput(yawCorrection, 0, climbPitch, 1);
                case STALL_DECELERATION -> new ControlInput(yawCorrection, 0, levelPitch, 0);
                case BRAKE -> new ControlInput(yawCorrection, -1, levelPitch, 0);
                case COMPLETE -> new ControlInput(0, 0, 0, 0);
            };
            CONTROLS.put(aircraft.getUUID(), control);
        }

        private void resetFlight() {
            ReflectiveAircraft.resetInternalState(aircraft);
            aircraft.setPos(anchor.x, anchor.y, anchor.z);
            aircraft.setDeltaMovement(Vec3.ZERO);
            aircraft.setYRot(0.0f);
            aircraft.setXRot(0.0f);
            ReflectiveAircraft.setRoll(aircraft, 0.0f);
            aircraft.fallDistance = 0.0f;
            CONTROLS.put(aircraft.getUUID(), new ControlInput(0, 0, 0, 0));
        }

        private double stat(String key, double fallback) {
            Double effective = effectiveStats.get(key);
            if (effective != null) {
                return effective;
            }
            return candidate.metadata().declaredProperties().getOrDefault(key, fallback);
        }

        private void keepChunksLoaded() {
            ServerLevel serverLevel = (ServerLevel) aircraft.level();
            ChunkPos center = aircraft.chunkPosition();
            for (int dx = -2; dx <= 2; dx++) {
                for (int dz = -2; dz <= 2; dz++) {
                    int chunkX = center.x + dx;
                    int chunkZ = center.z + dz;
                    long key = ChunkPos.asLong(chunkX, chunkZ);
                    if (!serverLevel.getForcedChunks().contains(key)) {
                        serverLevel.setChunkForced(chunkX, chunkZ, true);
                        ownedForcedChunks.add(key);
                    }
                }
            }
        }

        private void releaseOwnedChunks() {
            ServerLevel serverLevel = (ServerLevel) aircraft.level();
            for (long key : ownedForcedChunks) {
                ChunkPos chunk = new ChunkPos(key);
                serverLevel.setChunkForced(chunk.x, chunk.z, false);
            }
            ownedForcedChunks.clear();
        }

        private void fail(String message) {
            error = message;
            finished = true;
            phase = Phase.COMPLETE;
            CONTROLS.remove(aircraft.getUUID());
            CONTROL_HEARTBEATS.remove(aircraft.getUUID());
        }

        private boolean finished() {
            return finished;
        }

        private Phase phase() {
            return phase;
        }

        private void cleanup() {
            releaseOwnedChunks();
            CONTROLS.remove(aircraft.getUUID());
            CONTROL_HEARTBEATS.remove(aircraft.getUUID());
            if (!pilot.isRemoved()) {
                pilot.stopRiding();
                pilot.discard();
            }
            if (!aircraft.isRemoved()) {
                aircraft.discard();
            }
        }

        private Map<String, Object> result() {
            Map<String, Object> values = baseMetadata(candidate);
            values.put("status", error.isEmpty() ? "ok" : "failed");
            values.put("error", error);
            values.put("width", finite(aircraft.getBbWidth()));
            values.put("height", finite(aircraft.getBbHeight()));
            values.put("passenger_space", ReflectiveAircraft.passengerSpace(aircraft));
            for (Map.Entry<String, Double> entry : candidate.metadata().declaredProperties().entrySet()) {
                values.put("declared_" + entry.getKey(), finite(entry.getValue()));
            }
            for (Map.Entry<String, Double> entry : effectiveStats.entrySet()) {
                values.put("effective_" + entry.getKey(), finite(entry.getValue()));
            }

            double turnRate = turnSamples == 0 ? Double.NaN : turnDegrees / turnSamples * 20.0;
            double turnSpeed = turnSamples == 0 ? Double.NaN : turnSpeedSum / turnSamples;
            double turnRadius = !Double.isFinite(turnRate) || turnRate <= 0.0
                    ? Double.NaN : turnSpeed / Math.toRadians(turnRate);
            double climbRate = climbSamples == 0 ? Double.NaN : climbRateSum / climbSamples;
            double climbSpeed = climbSamples == 0 ? Double.NaN : climbSpeedSum / climbSamples;
            double pitchResponse = pitchSamples == 0 ? Double.NaN : pitchDegrees / pitchSamples * 20.0;
            double turnRetention = topSpeed <= 0.0 ? Double.NaN : turnSpeed / topSpeed;
            double turnVerticalRate = turnSamples == 0 ? Double.NaN : turnVerticalSpeedSum / turnSamples;
            boolean cleanAccelerationStart = accelerationInitialSpeed <= 0.50
                    && (!Double.isFinite(accelerationInitialEnginePower) || accelerationInitialEnginePower <= 0.021);
            List<String> qualityFlags = new ArrayList<>();
            if (!cleanAccelerationStart) {
                qualityFlags.add("contaminated_acceleration_start");
            }
            if (!brakeReachedTenPercent) {
                qualityFlags.add("brake_10_percent_not_reached");
            }
            if (Double.isFinite(turnRetention) && turnRetention > 1.02) {
                qualityFlags.add("turn_speed_exceeded_straight_speed");
            }

            values.put("profile_eligible", error.isEmpty() && cleanAccelerationStart);
            values.put("quality_flags", String.join("|", qualityFlags));
            values.put("accel_initial_speed_bps", finite(accelerationInitialSpeed));
            values.put("accel_initial_engine_power", finite(accelerationInitialEnginePower));
            values.put("top_speed_bps", finite(topSpeed));
            values.put("accel_time_50_s", finite(timeTo50));
            values.put("accel_time_90_s", finite(timeTo90));
            values.put("accel_time_95_s", finite(timeTo95));
            values.put("turn_rate_deg_s", finite(turnRate));
            values.put("turn_radius_blocks", finite(turnRadius));
            values.put("turn_speed_bps", finite(turnSpeed));
            values.put("turn_speed_retention", finite(turnRetention));
            values.put("turn_vertical_rate_bps", finite(turnVerticalRate));
            values.put("turn_altitude_change_blocks", finite(turnEndY - turnStartY));
            values.put("climb_rate_bps", finite(climbRate));
            values.put("climb_speed_bps", finite(climbSpeed));
            values.put("pitch_response_deg_s", finite(pitchResponse));
            values.put("stall_proxy_speed_bps", finite(stallProxySpeed));
            values.put("brake_initial_speed_bps", finite(brakeInitialSpeed));
            values.put("brake_distance_blocks", finite(brakeDistance));
            values.put("brake_time_50_s", finite(brakeTime50));
            values.put("brake_time_10_s", finite(brakeTime10));
            values.put("brake_reached_10_percent", brakeReachedTenPercent);
            return values;
        }
    }

    private static Map<String, Object> baseMetadata(Candidate candidate) {
        AircraftMetadata metadata = candidate.metadata();
        Map<String, Object> values = new LinkedHashMap<>();
        values.put("entity_id", candidate.id().toString());
        values.put("data_id", metadata.dataId().toString());
        values.put("variant_group", metadata.variantGroup());
        values.put("category", metadata.category().id());
        values.put("role", metadata.role());
        values.put("faction", metadata.faction());
        values.put("doctrine", metadata.doctrine());
        return values;
    }

    private static List<Map<String, Object>> readPrevious(Path latestFile) {
        if (!Files.isRegularFile(latestFile)) {
            return List.of();
        }
        try {
            JsonElement root = GSON.fromJson(Files.readString(latestFile, StandardCharsets.UTF_8), JsonElement.class);
            if (root == null || !root.isJsonArray()) {
                return List.of();
            }
            List<Map<String, Object>> values = new ArrayList<>();
            for (JsonElement element : root.getAsJsonArray()) {
                if (element.isJsonObject()) {
                    values.add(jsonObjectToMap(element.getAsJsonObject()));
                }
            }
            return values;
        } catch (IOException | RuntimeException ignored) {
            return List.of();
        }
    }

    private static Map<String, Object> jsonObjectToMap(JsonObject object) {
        Map<String, Object> map = new LinkedHashMap<>();
        for (Map.Entry<String, JsonElement> entry : object.entrySet()) {
            JsonElement value = entry.getValue();
            if (value.isJsonNull()) {
                map.put(entry.getKey(), null);
            } else if (value.isJsonPrimitive() && value.getAsJsonPrimitive().isNumber()) {
                map.put(entry.getKey(), value.getAsDouble());
            } else if (value.isJsonPrimitive() && value.getAsJsonPrimitive().isBoolean()) {
                map.put(entry.getKey(), value.getAsBoolean());
            } else if (value.isJsonPrimitive()) {
                map.put(entry.getKey(), value.getAsString());
            }
        }
        return map;
    }

    private static String buildCsv(List<Map<String, Object>> results) {
        List<String> columns = List.of(
                "entity_id", "variant_group", "category", "role", "faction", "doctrine", "status", "error",
                "profile_eligible", "quality_flags", "width", "height", "passenger_space",
                "effective_engineSpeed", "effective_acceleration", "effective_yawSpeed", "effective_pitchSpeed",
                "effective_lift", "effective_friction", "effective_glideFactor", "effective_mass",
                "effective_brakeFactor", "effective_stabilizer",
                "accel_initial_speed_bps", "accel_initial_engine_power",
                "top_speed_bps", "accel_time_50_s", "accel_time_90_s", "accel_time_95_s",
                "turn_rate_deg_s", "turn_radius_blocks", "turn_speed_bps", "turn_speed_retention",
                "turn_vertical_rate_bps", "turn_altitude_change_blocks",
                "climb_rate_bps", "climb_speed_bps", "pitch_response_deg_s", "stall_proxy_speed_bps",
                "brake_initial_speed_bps", "brake_distance_blocks", "brake_time_50_s", "brake_time_10_s",
                "brake_reached_10_percent"
        );
        StringBuilder csv = new StringBuilder(String.join(",", columns)).append('\n');
        for (Map<String, Object> result : results) {
            appendCsvRow(csv, result, columns);
        }
        return csv.toString();
    }

    private static String buildComparison(List<Map<String, Object>> previous, List<Map<String, Object>> current) {
        Map<String, Map<String, Object>> oldById = new HashMap<>();
        for (Map<String, Object> row : previous) {
            oldById.put(String.valueOf(row.get("entity_id")), row);
        }

        List<String> metrics = List.of(
                "top_speed_bps", "accel_time_90_s", "turn_rate_deg_s", "turn_radius_blocks",
                "climb_rate_bps", "stall_proxy_speed_bps", "brake_distance_blocks"
        );
        StringBuilder csv = new StringBuilder("entity_id,metric,previous,current,delta,delta_percent\n");
        for (Map<String, Object> row : current) {
            if (!"ok".equals(row.get("status")) || !Boolean.TRUE.equals(row.get("profile_eligible"))) {
                continue;
            }
            String id = String.valueOf(row.get("entity_id"));
            Map<String, Object> old = oldById.get(id);
            if (old == null || !"ok".equals(old.get("status"))
                    || !Boolean.TRUE.equals(old.get("profile_eligible"))) {
                continue;
            }
            for (String metric : metrics) {
                if ("brake_distance_blocks".equals(metric)
                        && (!Boolean.TRUE.equals(row.get("brake_reached_10_percent"))
                        || !Boolean.TRUE.equals(old.get("brake_reached_10_percent")))) {
                    continue;
                }
                Double oldValue = number(old.get(metric));
                Double newValue = number(row.get(metric));
                if (oldValue == null || newValue == null) {
                    continue;
                }
                double delta = newValue - oldValue;
                double percent = Math.abs(oldValue) < 1.0e-9 ? Double.NaN : delta / oldValue * 100.0;
                Map<String, Object> comparison = new LinkedHashMap<>();
                comparison.put("entity_id", id);
                comparison.put("metric", metric);
                comparison.put("previous", oldValue);
                comparison.put("current", newValue);
                comparison.put("delta", delta);
                comparison.put("delta_percent", Double.isFinite(percent) ? percent : "");
                appendCsvRow(csv, comparison,
                        List.of("entity_id", "metric", "previous", "current", "delta", "delta_percent"));
            }
        }
        return csv.toString();
    }

    private static Map<String, Object> buildProfiles(List<Map<String, Object>> results) {
        Map<String, Object> profiles = new LinkedHashMap<>();
        for (Map<String, Object> row : results) {
            if (!"ok".equals(row.get("status")) || !Boolean.TRUE.equals(row.get("profile_eligible"))) {
                continue;
            }
            Double top = number(row.get("top_speed_bps"));
            Double stall = number(row.get("stall_proxy_speed_bps"));
            Double turnSpeed = number(row.get("turn_speed_bps"));
            Double climbSpeed = number(row.get("climb_speed_bps"));
            Double brakeDistance = number(row.get("brake_distance_blocks"));
            boolean brakeComplete = Boolean.TRUE.equals(row.get("brake_reached_10_percent"));
            if (top == null || top <= 0.0) {
                continue;
            }

            double stallGuard = stall != null && stall > 0.0 ? stall * 1.20 : top * 0.38;
            Map<String, Object> profile = new LinkedHashMap<>();
            profile.put("category", row.get("category"));
            profile.put("role", row.get("role"));
            profile.put("faction", row.get("faction"));
            profile.put("doctrine", row.get("doctrine"));
            profile.put("stall_guard_speed_bps", stallGuard);
            profile.put("cruise_speed_bps", top * 0.75);
            profile.put("climb_target_speed_bps", climbSpeed != null && climbSpeed > 0.0
                    ? Math.max(stallGuard * 1.18, climbSpeed * 0.90)
                    : Math.max(stallGuard * 1.18, top * 0.62));
            profile.put("turn_speed_floor_bps", turnSpeed != null && turnSpeed > 0.0
                    ? turnSpeed * 0.85 : stallGuard * 1.10);
            profile.put("brake_lead_blocks", brakeComplete && brakeDistance != null
                    ? brakeDistance * 1.25 : null);
            profile.put("brake_distance_lower_bound_blocks", !brakeComplete ? brakeDistance : null);
            profile.put("measured_top_speed_bps", top);
            profiles.put(String.valueOf(row.get("variant_group")), profile);
        }
        return profiles;
    }

    private static void appendCsvRow(StringBuilder csv, Map<String, Object> values, List<String> columns) {
        for (int index = 0; index < columns.size(); index++) {
            if (index > 0) {
                csv.append(',');
            }
            Object value = values.get(columns.get(index));
            if (value == null) {
                continue;
            }
            String text = value instanceof Number number
                    ? String.format(Locale.ROOT, "%.6f", number.doubleValue())
                    : String.valueOf(value);
            csv.append('"').append(text.replace("\"", "\"\"")).append('"');
        }
        csv.append('\n');
    }

    @Nullable
    private static Double number(Object value) {
        return value instanceof Number number ? number.doubleValue() : null;
    }

    @Nullable
    private static Object finite(double value) {
        return Double.isFinite(value) ? value : null;
    }
}
