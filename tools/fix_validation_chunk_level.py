from pathlib import Path

path = Path('ww-debug-benchmark/src/main/java/com/wwdebug/benchmark/BenchmarkManager.java')
text = path.read_text(encoding='utf-8')
old = '''        private void keepChunksLoaded() {
            ChunkPos center = aircraft.chunkPosition();
            for (int dx = -2; dx <= 2; dx++) {
                for (int dz = -2; dz <= 2; dz++) {
                    int chunkX = center.x + dx;
                    int chunkZ = center.z + dz;
                    long key = ChunkPos.asLong(chunkX, chunkZ);
                    if (!level.getForcedChunks().contains(key)) {
                        level.setChunkForced(chunkX, chunkZ, true);
                        ownedForcedChunks.add(key);
                    }
                }
            }
        }

        private void releaseOwnedChunks() {
            for (long key : ownedForcedChunks) {
                ChunkPos chunk = new ChunkPos(key);
                level.setChunkForced(chunk.x, chunk.z, false);
            }
            ownedForcedChunks.clear();
        }
'''
new = '''        private void keepChunksLoaded() {
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
'''
if text.count(old) != 1:
    raise SystemExit(f'expected one chunk helper block, found {text.count(old)}')
path.write_text(text.replace(old, new, 1), encoding='utf-8')
