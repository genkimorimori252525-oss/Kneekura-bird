# Aircraft entity, livery, and AI profile matrix

Last verified: 2026-07-22

## Counting rules

The project has three different useful counts. They must not be used interchangeably.

1. **24 base Warfare Wings aircraft** — the gameplay and final AI acceptance set.
2. **90 Warfare Wings aircraft entities** — 24 base entities plus 66 `_schemeN` livery entities.
3. **26 default benchmark representative groups** — the 24 Warfare Wings base/livery groups plus two compatible `AirplaneEntity` groups supplied by the Immersive Aircraft dependency.

The fixed-input benchmark intentionally scans the complete Minecraft entity registry. When `includeVariants=false`, it collapses entities by `AircraftMetadata.variantGroup()`, but it does not restrict discovery to the `warfare_wings` namespace. Therefore the default all-category benchmark count is not the same thing as the Warfare Wings base-aircraft count.

## Profile inheritance rule

`AircraftMetadataResolver.baseEntityId()` removes a terminal `_schemeN` suffix. A livery entity therefore resolves its base aircraft data and measured profile when an exact livery-specific entry is absent.

Examples:

- `warfare_wings:a6m_scheme2` -> `warfare_wings:a6m`
- `warfare_wings:p47n_scheme3` -> `warfare_wings:p47n`
- `warfare_wings:g4m_scheme1` -> `warfare_wings:g4m`

A new paint scheme must not require a new flight model unless its actual physics differs from the base aircraft. If physics differ, it must receive an explicit measured profile instead of silently inheriting the base profile.

## Warfare Wings base-aircraft matrix

`Current doctrine` is the metadata currently present in the released aircraft JSON. `Target doctrine` is the final AI policy named in Issue #7.

| Base entity | Role | Current doctrine | Target doctrine | Registered livery entities | Total entity count |
|---|---|---|---|---:|---:|
| `a6m` | fighter | `turn_fighter` | `TurnFighter` | `scheme1`, `scheme2`, `scheme3` | 4 |
| `spitfire` | fighter | `turn_fighter` | `TurnFighter` | `scheme1`, `scheme2`, `scheme3` | 4 |
| `yak3` | fighter | `turn_fighter` | `TurnFighter` | `scheme1`, `scheme2`, `scheme3` | 4 |
| `bf109` | fighter | `energy_fighter` | `EnergyFighter` | `scheme1`, `scheme2`, `scheme3` | 4 |
| `f4u` | fighter | `energy_fighter` | `EnergyFighter` | `scheme1`, `scheme2`, `scheme3` | 4 |
| `f6f` | fighter | `energy_fighter` | `EnergyFighter` | `scheme1`, `scheme2`, `scheme3` | 4 |
| `fw190` | fighter | `energy_fighter` | `EnergyFighter` | `scheme1`, `scheme2`, `scheme3` | 4 |
| `ki61` | fighter | `energy_fighter` | `EnergyFighter` | `scheme1`, `scheme2`, `scheme3` | 4 |
| `ki84` | fighter | `energy_fighter` | `EnergyFighter` | `scheme1`, `scheme2`, `scheme3` | 4 |
| `mc202` | fighter | `energy_fighter` | `EnergyFighter` | `scheme1`, `scheme2`, `scheme3` | 4 |
| `mig3` | fighter | `energy_fighter` | `EnergyFighter` | `scheme1`, `scheme2`, `scheme3` | 4 |
| `p40e` | fighter | `energy_fighter` | `EnergyFighter` | `scheme1`, `scheme2`, `scheme3` | 4 |
| `p47n` | fighter | `energy_fighter` | `EnergyFighter` | `scheme1`, `scheme2`, `scheme3` | 4 |
| `p51d` | fighter | `energy_fighter` | `EnergyFighter` | `scheme1`, `scheme2`, `scheme3` | 4 |
| `b17` | bomber | `escort` | `LevelBomber` | `scheme1`, `scheme2`, `scheme3` | 4 |
| `b29` | bomber | `escort` | `LevelBomber` | `scheme1`, `scheme2`, `scheme3` | 4 |
| `g10n1` | bomber | `escort` | `LevelBomber` | `scheme1`, `scheme2` | 3 |
| `g10n2` | bomber | `escort` | `LevelBomber` | `scheme1`, `scheme2` | 3 |
| `he111` | bomber | `escort` | `LevelBomber` | `scheme1`, `scheme2`, `scheme3` | 4 |
| `d4y` | attacker | `attacker` | `DiveBomber` | `scheme1` | 2 |
| `ju87` | attacker | `attacker` | `DiveBomber` | `scheme1`, `scheme2`, `scheme3` | 4 |
| `sbd` | attacker | `attacker` | `DiveBomber` | `scheme1`, `scheme2` | 3 |
| `il2` | attacker | `attacker` | `GroundAttacker` | `scheme1`, `scheme2`, `scheme3` | 4 |
| `g4m` | torpedo bomber | `escort` | `TorpedoAttack` | `scheme1`, `scheme2` | 3 |

### Totals by role

| Role | Base aircraft | Livery entities | All Warfare Wings entities |
|---|---:|---:|---:|
| Fighter | 14 | 42 | 56 |
| Bomber | 5 | 13 | 18 |
| Attacker | 4 | 9 | 13 |
| Torpedo bomber | 1 | 2 | 3 |
| **Total** | **24** | **66** | **90** |

## Why the historical benchmark reported 26

`BenchmarkManager.discover()` iterates `BuiltInRegistries.ENTITY_TYPE`, creates each entity, accepts every controllable object for which `ReflectiveAircraft.isAirplane()` finds `immersive_aircraft.entity.AirplaneEntity` in the superclass chain, and then collapses only livery groups.

The Immersive Aircraft 1.20.1 dependency registers two of its own entities that extend `AirplaneEntity`:

- `immersive_aircraft:biplane` (`BiplaneEntity`)
- `immersive_aircraft:bamboo_hopper` (`BambooHopperEntity`)

Thus the default representative benchmark set is:

```text
24 Warfare Wings base/livery groups
+ 2 Immersive Aircraft AirplaneEntity groups
= 26 benchmark groups
```

The other Immersive Aircraft vehicles use different base classes and are rejected by `ReflectiveAircraft.isAirplane()`.

## Acceptance scope

- Final Warfare Wings AI qualification is defined against the **24 base aircraft**.
- Every registered `_schemeN` entity must resolve the correct base role, doctrine, and measured profile.
- The two dependency aircraft may remain visible in all-category physics discovery, but they are not part of the 24-aircraft Warfare Wings completion claim unless explicitly added to the project scope later.
- Automated reports must include both `entity_id` and `variant_group` so a 26-group benchmark cannot be mistaken for a 24-base-aircraft AI qualification.

## Sources of truth

- Base list and current role/doctrine: `tools/parse_aircraft_stats.py` and `tools/aircraft_stats.csv`
- Registered Warfare Wings entity/livery names: `assets/warfare_wings/lang/en_us.json`
- Livery inheritance: `AircraftMetadataResolver.baseEntityId()`
- Benchmark discovery/counting: `BenchmarkManager.discover()`
- Dependency registrations: Immersive Aircraft `Entities.java`
- Dependency superclass check: `BiplaneEntity` and `BambooHopperEntity`
