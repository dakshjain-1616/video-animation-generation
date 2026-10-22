import unittest

from vga.duration import (
    InfeasibleTimelineError,
    allocate_frames,
    planned_target,
    resolve_durations,
    scene_count_range,
)


class SceneCountTests(unittest.TestCase):
    def test_windows_are_feasible_for_their_targets(self):
        for target, (low, high) in ((20, (5, 8)), (30, (7, 10)), (45, (9, 13)), (60, (12, 20))):
            self.assertLessEqual(2 * low, target, f"{target}: {low} scenes cannot reach the target")
            self.assertGreaterEqual(5 * high, target, f"{target}: {high} scenes overshoot the target")


class ResolveDurationsTests(unittest.TestCase):
    def test_sums_exactly_to_each_target(self):
        for target in (20, 30, 45, 59.96, 45.5, 23.5):
            low, high = scene_count_range(min(60, max(20, target)))
            count = (low + high) // 2
            durations = resolve_durations([1.0] * count, target)
            self.assertAlmostEqual(sum(durations), target, delta=0.02)  # rounding is 3 decimals
            for duration in durations:
                self.assertGreaterEqual(duration, 2.0, f"target {target}")
                self.assertLessEqual(duration, 5.0, f"target {target}")

    def test_keeps_relative_weights_among_free_scenes(self):
        durations = resolve_durations([4, 4, 3, 2, 2], 20)
        self.assertEqual(durations[:2], [5.0, 5.0])  # pinned at the cap
        self.assertAlmostEqual(durations[2] / durations[3], 1.5, places=3)  # 3:2 preserved
        self.assertAlmostEqual(sum(durations), 20, places=2)

    def test_pins_extremes_and_rebalances(self):
        # Six heavy scenes at a 20s target: they start over 5s each and settle inside bounds.
        durations = resolve_durations([10, 10, 10, 10, 10, 10], 20)
        self.assertAlmostEqual(sum(durations), 20, places=2)
        self.assertTrue(all(2 <= value <= 5 for value in durations))

    def test_uneven_extremes_still_land_on_target(self):
        # One dominant scene drags two minimal ones; the sum must still be exact.
        durations = resolve_durations([100, 1, 1], 7.5)
        self.assertAlmostEqual(sum(durations), 7.5, places=2)
        self.assertTrue(all(2 <= value <= 5 for value in durations))

    def test_rejects_impossible_counts(self):
        # 4 scenes, 30s target: max reach 20s.
        with self.assertRaises(InfeasibleTimelineError):
            resolve_durations([1.0] * 4, 30)
        # 10 scenes, 10s target: minimum reach 20s.
        with self.assertRaises(InfeasibleTimelineError):
            resolve_durations([1.0] * 10, 10)

    def test_rejects_empty_weights(self):
        with self.assertRaises(ValueError):
            resolve_durations([], 30)


class FrameTests(unittest.TestCase):
    def test_frames_sum_to_composition_length(self):
        for target, count in ((20, 6), (59.96, 14)):
            durations = resolve_durations([1.0] * count, target)
            frames = allocate_frames(durations, 30)
            self.assertEqual(sum(frames), round(target * 30), f"target {target}")
            self.assertTrue(all(frame > 0 for frame in frames))

    def test_planned_target_pulls_in_the_ceiling(self):
        self.assertEqual(planned_target(60), 59.96)
        self.assertEqual(planned_target(59.9), 59.96)
        self.assertEqual(planned_target(45), 45)


if __name__ == "__main__":
    unittest.main()
