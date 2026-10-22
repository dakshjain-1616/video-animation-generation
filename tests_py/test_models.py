import unittest

from vga.models import Scene, Storyboard, duration_pass, storyboard_issues
from vga.plan import MAX_TITLE_CHARS, PlannedScene, Plan, clip_title, repair_plan


def board(target: float, seconds: list[float], surfaces: list[str], kinds=None) -> Storyboard:
    frames = [round(value * 30) for value in seconds]
    return Storyboard(
        id="p",
        title="test",
        category="explainer",
        target=target,
        fps=30,
        width=1920,
        height=1080,
        entry="src/generated/p/entry.tsx",
        scenes=[
            Scene(
                id=f"scene{index + 1:02d}",
                title="TEST",
                kind=(kinds or _kinds(len(seconds)))[index],
                surface=surfaces[index],  # type: ignore[arg-type]
                seconds=seconds[index],
                frames=frames[index],
            )
            for index in range(len(seconds))
        ],
    )


def _kinds(count: int) -> list[str]:
    return ["open"] + ["body"] * (count - 2) + ["close"]


class WindowTests(unittest.TestCase):
    def test_clamps_at_platform_bounds(self):
        self.assertTrue(duration_pass(21.9, 20))
        self.assertFalse(duration_pass(19.9, 20))
        self.assertTrue(duration_pass(59.9, 60))
        self.assertFalse(duration_pass(60.01, 60))

    def test_flags_structural_issues(self):
        issues = storyboard_issues(board(30, [2, 2, 2, 2, 2], ["paper"] * 5))
        self.assertEqual(issues, ["storyboard totals 10.00s, outside tolerance for target 30s"])

    def test_flags_adjacent_nights(self):
        issues = storyboard_issues(board(20, [4, 4, 4, 4, 4], ["night", "night", "paper", "paper", "night"]))
        self.assertTrue(any("night surfaces" in issue for issue in issues))

    def test_duration_uses_frames_at_minimum_platform_length(self):
        rounded_seconds = [2.727, 2.727, 2.700, 3.633, 2.700, 2.727, 2.727]
        exact_frames = [82, 82, 81, 110, 81, 82, 82]
        storyboard = board(20, rounded_seconds, ["paper"] * 7)
        for scene, frames in zip(storyboard.scenes, exact_frames):
            scene.frames = frames
        self.assertAlmostEqual(storyboard.seconds(), 20)
        self.assertEqual(storyboard_issues(storyboard), [])

    def test_flags_bad_kinds(self):
        issues = storyboard_issues(board(20, [4] * 5, ["paper"] * 5, kinds=["body", "body", "body", "body", "body"]))
        self.assertEqual(len([issue for issue in issues if 'kind' in issue]), 2)

    def test_flags_duplicate_ids(self):
        broken = board(20, [4] * 5, ["paper"] * 5)
        broken.scenes[1].id = broken.scenes[0].id
        self.assertTrue(any("duplicate" in issue for issue in storyboard_issues(broken)))


class RepairPlanTests(unittest.TestCase):
    def plan(self, surfaces: list[str], weights: list[float]) -> Plan:
        return Plan(
            idea="its topic here",
            target=30,
            title="TEST VIDEO",
            angle="one mechanism",
            audience="curious adults",
            scenes=[
                PlannedScene("scene01", "FIRST", "body", surfaces[i] if i < len(surfaces) else "paper", weights[i % len(weights)])
                for i in range(len(surfaces))
            ],
        )

    def test_kinds_are_positional(self):
        plan = self.plan(["night"] + ["paper"] * 9, [3] * 10)
        repair_plan(plan)
        self.assertEqual(plan.scenes[0].kind, "open")
        self.assertEqual(plan.scenes[-1].kind, "close")
        self.assertEqual([scene.kind for scene in plan.scenes[1:-1]], ["body"] * (len(plan.scenes) - 2))

    def test_never_two_nights_in_a_row(self):
        plan = self.plan(["night", "night", "night", "night", "night", "night", "night", "night", "night", "night"], [3] * 10)
        repair_plan(plan)
        for previous, current in zip(plan.scenes, plan.scenes[1:]):
            self.assertNotEqual((previous.surface, current.surface), ("night", "night"))
        self.assertIn(plan.scenes[0].surface, ("night", "paper"))


class TitleTests(unittest.TestCase):
    def test_long_titles_cut_on_a_word_boundary(self):
        clipped = clip_title("SHIPPING HAPPENS BEFORE THE REVIEW COMPLETES")
        self.assertLessEqual(len(clipped), MAX_TITLE_CHARS)
        self.assertTrue(clipped.endswith("…"))
        self.assertNotIn("HAPPE…", clipped)

    def test_short_titles_are_uppercased_untouched(self):
        self.assertEqual(clip_title("  a small title  "), "A SMALL TITLE")


class StoryboardRoundTripTests(unittest.TestCase):
    def test_to_dict_matches_fields(self):
        data = board(30, [2.5, 3.5, 4, 5, 5], ["paper"] * 5).to_dict()
        self.assertEqual(data["category"], "explainer")
        self.assertEqual(data["scenes"][0]["seconds"], 2.5)
        self.assertEqual(data["scenes"][0]["frames"], 75)


if __name__ == "__main__":
    unittest.main()
