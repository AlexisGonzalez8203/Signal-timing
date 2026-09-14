# signal-timing

Validation of traffic signal timing parameters and operational compliance.

Given a NEMA ring-barrier timing plan, this library answers three questions:

1. **Is it runnable?** Do the splits sum to the cycle length, do the rings reach
   the barrier together, does every split cover its own clearance intervals?
2. **Is it legal?** Do the yellow, red clearance, and pedestrian intervals fall
   within MUTCD limits?
3. **Is it adequate?** Are those intervals long enough for the speed, grade, and
   geometry of the approach they actually serve?

The third question is the one that catches real problems. A 3.0 s yellow is
legal at every intersection in the country and dangerously short on a 55 mph
approach.

## Install

```bash
pip install -e ".[dev]"
```

Requires Python 3.10+. No runtime dependencies.

## Use

### Command line

```bash
signal-timing examples/eight_phase_coordinated.json
```

```
Timing plan: Main St & Oak Ave -- AM Peak
============================================================
No findings.
============================================================
0 error(s), 0 warning(s), 0 info across 18 rule(s) -- PASS
```

A plan with problems reports each one with its citation:

```bash
signal-timing examples/faulty_plan.json
```

```
ERROR    Phase 2 yellow is 2.5 s but 4.3 s is required at 45 mph on a +0.0% grade.
           ITE Traffic Control Devices Handbook -- change and clearance intervals
ERROR    Phase 6 pedestrian change interval is 8.0 s but 13.7 s is required to cross 48 ft at 3.5 ft/s.
           MUTCD Ch. 4 -- Pedestrian Intervals and Signal Phases
ERROR    Barrier group 1: ring 2 sums to 65.0 s but ring 1 sums to 60.0 s (differs by 5.0 s).
           NEMA TS 2 -- ring, barrier, and concurrency structure
...
```

Exit codes: `0` clean, `1` findings, `2` the file could not be read as a plan.
That makes it usable as a CI gate on a timing-plan repository.

Options:

| Flag | Effect |
| --- | --- |
| `--format json` | Machine-readable output |
| `--quiet` | Hide INFO findings |
| `--strict` | Treat warnings as failures |
| `--walking-speed FPS` | Override the pedestrian design walking speed |
| `--max-cycle SECONDS` | Override the practical maximum cycle length |

### Library

```python
from signal_timing import Approach, Phase, TimingPlan, validate

plan = TimingPlan(
    name="Main St & Oak Ave -- AM Peak",
    cycle_length_s=120.0,
    offset_s=45.0,
    coordinated_phases=(2, 6),
    phases={
        2: Phase(
            number=2,
            name="Main St NB through",
            min_green_s=15.0,
            yellow_s=4.5,
            red_clearance_s=1.5,
            split_s=55.0,
            walk_s=7.0,
            ped_change_s=14.0,
            approach=Approach(
                speed_mph=45.0,
                clearance_distance_ft=60.0,
                crossing_distance_ft=48.0,
            ),
        ),
        # ... remaining phases
    },
)

report = validate(plan)
print(report.to_text())

for finding in report.errors:
    print(finding.rule_id, finding.phase, finding.message)
```

The interval formulas are usable on their own:

```python
from signal_timing import yellow_change_interval, red_clearance_interval

yellow_change_interval(45.0)                  # 4.30 s
yellow_change_interval(45.0, grade=-0.04)     # 4.79 s on a 4% downgrade
red_clearance_interval(60.0, 45.0)            # 1.21 s
```

## Plan format

Plans are JSON. `rings`, `barrier_groups`, and `offset_s` are optional — rings
and barrier groups default to the standard NEMA eight-phase assignment,
filtered to the phases actually present.

```json
{
  "name": "Main St & Oak Ave -- AM Peak",
  "cycle_length_s": 120.0,
  "offset_s": 45.0,
  "coordinated_phases": [2, 6],
  "rings": [[1, 2, 3, 4], [5, 6, 7, 8]],
  "barrier_groups": [[1, 2, 5, 6], [3, 4, 7, 8]],
  "phases": [
    {
      "number": 2,
      "name": "Main St NB through",
      "min_green_s": 15.0,
      "max_green_s": 60.0,
      "yellow_s": 4.5,
      "red_clearance_s": 1.5,
      "split_s": 55.0,
      "walk_s": 7.0,
      "ped_change_s": 14.0,
      "approach": {
        "speed_mph": 45.0,
        "grade": 0.0,
        "clearance_distance_ft": 60.0,
        "crossing_distance_ft": 48.0
      }
    }
  ]
}
```

`split_s` follows the NEMA convention: it is the phase's whole allocation,
including its own yellow and red clearance. Green time is derived, not stored.

A phase with no `approach` is still checked structurally and against the MUTCD
ranges; only the adequacy rules are skipped, since they have nothing to compute
against.

## Rules

Eighteen rules run by default, in three groups.

### Structural — `signal_timing.rules.structure`

| ID | Checks |
| --- | --- |
| `STRUCT-ASSIGNMENT` | Each phase is in exactly one ring and one barrier group |
| `STRUCT-SPLIT-CLEARANCE` | Split covers the phase's yellow and red clearance |
| `STRUCT-SPLIT-MIN-GREEN` | Split accommodates minimum green plus clearance |
| `STRUCT-MAX-GREEN` | Maximum green is at least the minimum green |
| `STRUCT-RING-SUM` | Rings consume equal time within each barrier group |
| `STRUCT-CYCLE-SUM` | Barrier group durations sum to the cycle length |
| `STRUCT-PED-FITS` | WALK plus pedestrian change interval fits in the split |

### Coordination — `signal_timing.rules.coordination`

| ID | Checks |
| --- | --- |
| `COORD-CYCLE-RANGE` | Cycle length is positive and workable |
| `COORD-OFFSET-RANGE` | Offset is non-negative and less than the cycle |
| `COORD-PHASES-SET` | A coordinated plan designates its coordinated phases |
| `COORD-PHASES-CONCURRENT` | Coordinated phases can actually run together |

### Intervals — `signal_timing.rules.mutcd`

| ID | Checks |
| --- | --- |
| `MUTCD-Y-RANGE` | Yellow is between 3 and 6 seconds |
| `MUTCD-R-RANGE` | Red clearance does not exceed 6 seconds |
| `MUTCD-WALK-MIN` | WALK meets the 7 s normal / 4 s absolute minimum |
| `MUTCD-PCI-ADEQUACY` | Pedestrian change interval covers the crossing at 3.5 ft/s |
| `ITE-Y-ADEQUACY` | Yellow covers the ITE kinematic requirement |
| `ITE-R-ADEQUACY` | Red clearance covers the conflict area |
| `ITE-MIN-GREEN` | Minimum green meets the policy floor |

**Severity.** `ERROR` marks a violation of a mandatory requirement or a plan
that cannot run as entered. `WARNING` marks a departure from guidance that an
engineer may accept with documented judgment. `INFO` is advisory — most often,
that a check could not be performed because input data was missing.

## Formulas

Yellow change interval (ITE):

```
Y = t + V / (2a + 2gG)
```

where `t` is perception-reaction time (1.0 s), `V` the approach speed in ft/s,
`a` the deceleration rate (10 ft/s²), `g` gravity (32.2 ft/s²), and `G` the
grade as a decimal — positive uphill, negative downhill. A downgrade lengthens
the interval.

Red clearance interval (ITE):

```
R = (W + L) / V
```

where `W` is the distance from the stop line to the far edge of the conflicting
path and `L` the design vehicle length (20 ft).

Pedestrian change interval (MUTCD):

```
PCI = crossing distance / 3.5 ft/s
```

Every constant above is a default on `Policy`, not a literal in the rules.

## Local policy

Agencies that adopt stricter standards construct a `Policy` rather than editing
rules:

```python
from signal_timing import Policy, default_ruleset, validate

policy = Policy(
    yellow_min_s=3.5,           # local floor above the MUTCD's 3.0
    walking_speed_fps=3.0,      # slower design pedestrian
    min_green_floor_s=7.0,
    max_cycle_length_s=150.0,
)

report = validate(plan, policy=policy)
```

Rules can also be selected individually:

```python
from signal_timing.rules import RuleSet, structure_rules

report = validate(plan, ruleset=RuleSet("structure only").extend(structure_rules()))
```

Custom rules need only an `id`, a `description`, and a `check(plan)` that yields
`Finding` objects — see `signal_timing.rules.base.Rule`.

## Tests

```bash
pytest
```

187 tests covering the formulas against published interval values, the model's
structural validation, every rule's positive and negative cases, policy
overrides, report rendering, and the CLI's exit codes.

## Scope

This validates a timing plan as entered. It does not calculate optimal splits,
model delay or queues, evaluate progression bandwidth across a corridor, or read
controller-vendor database formats. Those are the obvious next pieces to build
on top of the model in `signal_timing.model`.

The MUTCD citations name chapters rather than section numbers, since section
numbering moved between the 2009 and 2023 editions. Verify against the edition
your agency has adopted before relying on this in production.
