#!/usr/bin/env python3
"""Compare Java corridor decisions with exact rational segment-box intersections."""

from fractions import Fraction
import argparse
import hashlib
import json
import math
import platform
import random
import subprocess
import sys


def exact_intersects(start, end, lower, upper):
    """Inclusive intersection of the exact rational values of finite binary64 inputs."""
    first, last = Fraction(0), Fraction(1)
    for origin, finish, minimum, maximum in zip(start, end, lower, upper):
        origin, finish, minimum, maximum = (Fraction.from_float(float(value))
                                            for value in (origin, finish, minimum, maximum))
        difference = finish - origin
        if difference == 0:
            if origin < minimum or origin > maximum:
                return False
            continue
        enter, exit = (minimum - origin) / difference, (maximum - origin) / difference
        if enter > exit:
            enter, exit = exit, enter
        first, last = max(first, enter), min(last, exit)
        if first > last:
            return False
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--java", required=True)
    parser.add_argument("--classpath", required=True)
    args = parser.parse_args()
    rng = random.Random(42507)
    cases = []
    for scale, count in ((1e8, 12000), (1e-120, 1000), (1e150, 1000)):
        for _ in range(count):
            start = [rng.uniform(-scale, scale) for _ in range(3)]
            end = [rng.uniform(-scale, scale) for _ in range(3)]
            t = rng.random()
            point = [start[i] + (end[i] - start[i]) * t for i in range(3)]
            lower = [math.nextafter(value, -math.inf) for value in point]
            upper = [math.nextafter(value, math.inf) for value in point]
            # High, narrow boxes exercise cases the legacy center sphere can miss.
            upper[1] += scale * 0.000001
            cases.append((lower, upper, 0.6, start, end))
    for _ in range(1000):
        x = rng.uniform(10, 90)
        cases.append(([x - 0.3, 104, -0.3], [x + 0.3, 107, 0.3], 0.6,
                      [0., 100., 0.], [100., 100., 0.]))

    expected = [exact_intersects(start, end, lower, upper)
                for lower, upper, _, start, end in cases]
    input_text = "".join(" ".join(float(v).hex() for v in (*lower, *upper, width, *start, *end)) + "\n"
                         for lower, upper, width, start, end in cases)
    process = subprocess.run([args.java, "-cp", args.classpath,
                              "com.wwdebug.autopilot.ProtectedCorridorGeometryCheck", "--batch"],
                             input=input_text, capture_output=True, text=True, timeout=60)
    answers = [line == "1" for line in process.stdout.splitlines() if line in ("0", "1")]
    if process.returncode != 0 or len(answers) != len(cases):
        print(json.dumps({"passed": False, "error": "Java batch failed or returned a different case count",
                          "exit": process.returncode, "expected": len(cases), "received": len(answers),
                          "stderr": process.stderr}))
        return 1
    false_negatives = [index for index, (actual, exact) in enumerate(zip(answers, expected))
                       if exact and not actual]
    separated_controls = answers[-1000:]
    result = {"passed": not false_negatives and not any(separated_controls),
              "seed": 42507, "generator": "12000 near-corner scale 1e8, 1000 each scales 1e-120 and 1e150, 1000 separated controls",
              "python_version": platform.python_version(),
              "input_sha256": hashlib.sha256(input_text.encode("utf-8")).hexdigest(),
              "exact_decisions_sha256": hashlib.sha256(bytes(expected)).hexdigest(),
              "java_decisions_sha256": hashlib.sha256(bytes(answers)).hexdigest(),
              "cases": len(cases), "exact_intersections": sum(expected),
              "false_negative_count": len(false_negatives), "first_false_negatives": false_negatives[:5],
              "separated_controls_blocked": sum(separated_controls),
              "nonintersections_blocked": sum(actual and not exact for actual, exact in zip(answers, expected)),
              "scope": "synthetic exact segment-box comparison; not actual projectile or GameTest evidence"}
    print(json.dumps(result, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
