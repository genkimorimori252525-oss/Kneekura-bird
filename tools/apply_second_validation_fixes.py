from pathlib import Path

path = Path('ww-debug-benchmark/src/main/java/com/wwdebug/benchmark/BenchmarkManager.java')
text = path.read_text(encoding='utf-8')

replacements = [
    (
'''                boolean fullyValid = results.stream().allMatch(row -> "ok".equals(row.get("status"))
                        && Boolean.TRUE.equals(row.get("profile_eligible")));''',
'''                boolean fullyValid = results.stream().allMatch(row -> "ok".equals(row.get("status")));''',
        'successful baseline eligibility'
    ),
    (
'''                case STRAIGHT_ACCELERATION -> {
                    if (phaseTick == 0) {
                        accelerationInitialSpeed = horizontalSpeed;
                        accelerationInitialEnginePower = ReflectiveAircraft.enginePower(aircraft);
                    }
                    accelerationSpeeds.add(horizontalSpeed);''',
'''                case STRAIGHT_ACCELERATION -> {
                    accelerationSpeeds.add(horizontalSpeed);''',
        'acceleration first-sample capture'
    ),
    (
'''                case PREPARE -> {
                    resetFlight();
                    yield Phase.STRAIGHT_ACCELERATION;
                }''',
'''                case PREPARE -> {
                    accelerationInitialSpeed = aircraft.getDeltaMovement().horizontalDistance() * 20.0;
                    accelerationInitialEnginePower = ReflectiveAircraft.enginePower(aircraft);
                    resetFlight();
                    yield Phase.STRAIGHT_ACCELERATION;
                }''',
        'pre-throttle acceleration baseline capture'
    ),
    (
'''            boolean cleanAccelerationStart = accelerationInitialSpeed <= 0.50
                    && (!Double.isFinite(accelerationInitialEnginePower) || accelerationInitialEnginePower <= 0.05);''',
'''            boolean cleanAccelerationStart = accelerationInitialSpeed <= 0.50
                    && (!Double.isFinite(accelerationInitialEnginePower) || accelerationInitialEnginePower <= 0.021);''',
        'pre-throttle engine threshold'
    ),
    (
'''            for (String metric : metrics) {
                Double oldValue = number(old.get(metric));''',
'''            for (String metric : metrics) {
                if ("brake_distance_blocks".equals(metric)
                        && (!Boolean.TRUE.equals(row.get("brake_reached_10_percent"))
                        || !Boolean.TRUE.equals(old.get("brake_reached_10_percent")))) {
                    continue;
                }
                Double oldValue = number(old.get(metric));''',
        'incomplete brake comparison filter'
    ),
    (
'''            Double brakeDistance = number(row.get("brake_distance_blocks"));
            if (top == null || top <= 0.0) {''',
'''            Double brakeDistance = number(row.get("brake_distance_blocks"));
            boolean brakeComplete = Boolean.TRUE.equals(row.get("brake_reached_10_percent"));
            if (top == null || top <= 0.0) {''',
        'brake completeness profile input'
    ),
    (
'''            profile.put("brake_lead_blocks", brakeDistance != null ? brakeDistance * 1.25 : null);
            profile.put("measured_top_speed_bps", top);''',
'''            profile.put("brake_lead_blocks", brakeComplete && brakeDistance != null
                    ? brakeDistance * 1.25 : null);
            profile.put("brake_distance_lower_bound_blocks", !brakeComplete ? brakeDistance : null);
            profile.put("measured_top_speed_bps", top);''',
        'safe incomplete brake profile output'
    ),
]

for old, new, label in replacements:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected one match, found {count}')
    text = text.replace(old, new, 1)

path.write_text(text, encoding='utf-8')
