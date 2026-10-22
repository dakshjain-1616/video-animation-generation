"""Duration algebra: how plan seconds become exact render frames.

No narration, no holds to solve: the planner proposes a weight per scene, and
these functions turn those weights into scene lengths that sum exactly to the
target and frame counts that sum exactly to the composition length.
"""

from __future__ import annotations

MIN_SCENE_SECONDS = 2.0
MAX_SCENE_SECONDS = 5.0
# Containers add a few milliseconds of muxer priming, and 60.01s is outside the
# platform bound even though 60.00s is not, so the ceiling plans a hair short.
CEILING_SECONDS = 59.96


class InfeasibleTimelineError(ValueError):
    pass


def scene_count_range(target: float) -> tuple[int, int]:
    """Scene count bounds that keep every length inside 2.0-5.0s feasible."""
    if target <= 20:
        return 5, 8
    if target <= 30:
        return 7, 10
    if target <= 45:
        return 9, 13
    return 12, 20


def planned_target(target: float) -> float:
    return CEILING_SECONDS if target >= 59.9 else target


def resolve_durations(weights: list[float], target: float) -> list[float]:
    """Scale scene weights to lengths summing exactly to `target`, 2.0-5.0s each.

    Relative weights are preserved among scenes that fit inside the bounds.
    Raises rather than padding, speeding up, or silently missing the target.
    """
    if not weights:
        raise ValueError("No scenes to time.")
    count = len(weights)
    if not MIN_SCENE_SECONDS * count <= target <= MAX_SCENE_SECONDS * count:
        raise InfeasibleTimelineError(
            f"{count} scenes can only fill {MIN_SCENE_SECONDS * count:.1f}-"
            f"{MAX_SCENE_SECONDS * count:.1f}s, target is {target:.2f}s."
        )

    weights = [max(weight, 1e-6) for weight in weights]
    durations = [0.0] * count
    locked: set[int] = set()

    for _ in range(count):
        free = [i for i in range(count) if i not in locked]
        if not free:
            break
        scale = (target - sum(durations[i] for i in locked)) / sum(weights[i] for i in free)
        pinned = False
        for i in free:
            raw = weights[i] * scale
            if raw >= MAX_SCENE_SECONDS - 1e-12:
                durations[i], pinned = MAX_SCENE_SECONDS, True
                locked.add(i)
            elif raw <= MIN_SCENE_SECONDS + 1e-12:
                durations[i], pinned = MIN_SCENE_SECONDS, True
                locked.add(i)
            else:
                durations[i] = raw
        if not pinned:
            break  # free scenes now sum exactly to the residual

    # Feasibility (checked above) guarantees one sweep can clear any slack.
    residue = target - sum(durations)
    for i in range(count):
        if abs(residue) <= 1e-9:
            break
        room = (MAX_SCENE_SECONDS - durations[i]) if residue > 0 else (durations[i] - MIN_SCENE_SECONDS)
        shift = min(abs(residue), max(room, 0.0))
        durations[i] += shift if residue > 0 else -shift
        residue = target - sum(durations)
    if abs(residue) > 1e-6:
        raise InfeasibleTimelineError(f"Cannot place {residue:.3f}s of slack inside the 2-5s scene bounds.")

    durations = [round(value, 3) for value in durations]
    if abs(target - sum(durations)) > 0.001 * count:  # rounding drift at 3 decimals
        raise InfeasibleTimelineError(f"Rounding drift exceeds 1ms per scene for target {target:.3f}s.")
    return durations


def allocate_frames(durations: list[float], fps: int) -> list[int]:
    """Cumulative rounding: per-scene frames always sum to the composition length."""
    frames: list[int] = []
    elapsed = 0.0
    previous = 0
    for duration in durations:
        elapsed += duration
        cumulative = round(elapsed * fps)
        frames.append(cumulative - previous)
        previous = cumulative
    return frames
