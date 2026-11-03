package com.wwdebug.autopilot;

import com.wwdebug.benchmark.WWDebugBenchmarkMod;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.entity.Entity;

import java.util.UUID;

/** Opt-in GameTest registration evidence; never force-loads or changes entity timing. */
final class MutualDogfightUuidFixture {
    private MutualDogfightUuidFixture() {
    }

    static void add(ServerLevel level, Entity entity, UUID expectedUuid, String role) {
        boolean accepted = false;
        Entity visible = null;
        try {
            accepted = level.addFreshEntity(entity);
            visible = level.getEntity(expectedUuid);
            String status = MutualDogfightUuidOrder.registrationStatus(accepted,
                    entity.isAddedToWorld(), entity.isRemoved(), expectedUuid, entity.getUUID(),
                    entity, visible);
            WWDebugBenchmarkMod.LOGGER.info(
                    "Mutual GameTest UUID registration role={} uuid={} accepted=true lookup={}",
                    role, expectedUuid, status);
        } catch (RuntimeException failure) {
            WWDebugBenchmarkMod.LOGGER.error(
                    "Mutual GameTest UUID registration failed role={} expected={} actual={} accepted={} added_to_world={} removed={} lookup={}",
                    role, expectedUuid, entity.getUUID(), accepted, entity.isAddedToWorld(),
                    entity.isRemoved(), visible == null ? "hidden_or_unavailable" : "present");
            throw new IllegalStateException("mutual_uuid_registration_failed:" + role, failure);
        }
    }
}
