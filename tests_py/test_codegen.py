import unittest
from unittest import mock

from vga.codegen import (
    _fill_issues,
    _legibility_issues,
    _motion_issues,
    _scene_keys,
    contract_errors,
    error_hints,
    normalize_imports,
    normalize_types,
    strip_fences,
    typecheck,
    write_entry,
)
from vga.llm import InfraError
from vga.models import Scene, Storyboard
from vga.plan import PlannedScene, Plan

GOOD = '''
import type React from "react";
import { BodyScene } from "../../components/foundation/BodyScene";
import { CardScene } from "../../components/foundation/CardScene";

const HookScene = () => <CardScene surface="night" lines={["THE QUESTION"]} highlight={[0]} />;

const PayoffScene = () => <CardScene surface="night" lines={["THAT IS WHY"]} />;

export const SCENES: Record<string, React.FC> = {
  hook: HookScene,
  payoff: PayoffScene,
};
'''


def plan_with(*ids: str) -> Plan:
    count = len(ids)
    return Plan(
        idea="its topic here",
        target=30,
        title="TEST",
        angle="one mechanism",
        audience="curious adults",
        scenes=[
            PlannedScene(
                ids[i], "TITLE", "open" if i == 0 else ("close" if i == count - 1 else "body"),
                "night", 3.0,
            )
            for i in range(count)
        ],
    )


def board_of(plan: Plan) -> Storyboard:
    return Storyboard(
        id="p", title="t", category="explainer", target=30, fps=30, width=1920, height=1080,
        entry="src/generated/p/entry.tsx",
        scenes=[
            Scene(scene.id, scene.title, scene.kind, scene.surface, 3.0, 90)  # type: ignore[arg-type]
            for scene in plan.scenes
        ],
    )


class ContractTests(unittest.TestCase):
    def test_hardcoded_color_failure_has_an_actionable_repair_hint(self):
        hint = error_hints("hardcoded hex color (use useTheme tokens)")
        self.assertIn("useTheme()", hint)
        self.assertIn("colors.accent", hint)

    def test_accepts_a_conforming_scene_file(self):
        self.assertEqual(contract_errors(GOOD, plan_with("hook", "payoff")), [])

    def test_timing_props_in_frames_rejected(self):
        bad = GOOD.replace(
            "export const SCENES: Record<string, React.FC> = {",
            'export const SCENES: Record<string, React.FC> = {\n'
            '  hook: () => (<SceneShell surface="paper"><KineticHeading lines={["X"]} x={0} y={0} delay={60} stagger={100} /></SceneShell>),',
        )
        errors = contract_errors(bad, plan_with("hook", "payoff"))
        self.assertTrue(any("timing props are SECONDS" in error for error in errors), errors)

    def test_rejects_external_markup_and_clock_driven_animation(self):
        for snippet in (
            '<iframe src="https://example.com" />',
            '<div dangerouslySetInnerHTML={{__html: "code"}} />',
            '<div style={{animation: "spin 1s"}} />',
            '<img src="https://example.com/a.png" />',
        ):
            self.assertTrue(contract_errors(snippet + GOOD, plan_with("hook", "payoff")))

    def test_accepts_custom_canvas_scene(self):
        source = GOOD.replace('BodyScene', 'CanvasScene')
        self.assertEqual(contract_errors(source, plan_with("hook", "payoff")), [])

    def test_requires_every_planned_scene_key(self):
        errors = contract_errors(GOOD, plan_with("hook", "body1", "payoff"))
        self.assertEqual(errors, ['SCENES is missing the key "body1"'])

    def test_rejects_unplanned_keys(self):
        errors = contract_errors(GOOD, plan_with("hook", "extra", "payoff"))
        self.assertEqual(errors, ['SCENES is missing the key "extra"'])

    def test_rejects_disallowed_imports(self):
        for snippet in (
            'import fs from "fs";\n' + GOOD,
            'import { execSync } from "node:child_process";\n' + GOOD,
            'import { z } from "zod";\n' + GOOD,
        ):
            errors = contract_errors(snippet, plan_with("hook", "payoff"))
            self.assertTrue(any("import" in error for error in errors), snippet)

    def test_rejects_forbidden_apis(self):
        for snippet, label in (
            ('const x = fetch("https://a");\n' + GOOD, "fetch()"),
            ('setTimeout(() => {}, 10);\n' + GOOD, "timers"),
            ("const seed = Math.random();\n" + GOOD, "Math.random"),
            ('const driver = eval("1+1");\n' + GOOD, "eval()"),
            ('const mod = await import("x");\n' + GOOD, "dynamic import()"),
            ("const start = process.argv;\n" + GOOD, "process"),
            ("if (typeof window !== 'undefined') {}\n" + GOOD, "DOM"),
        ):
            errors = contract_errors(snippet, plan_with("hook", "payoff"))
            self.assertTrue(any(label in error for error in errors), snippet)

    def test_requires_the_scenes_export(self):
        errors = contract_errors("export {};", plan_with("hook"))
        self.assertTrue(any("export const SCENES" in error for error in errors))

    def test_rejects_direct_house_primitives(self):
        bad = GOOD.replace(
            "<CardScene surface=\"night\" lines={[\"THE QUESTION\"]} highlight={[0]} />",
            '<SceneShell surface="night"><KineticHeading lines={["THE QUESTION"]} x={96} y={300} /></SceneShell>',
        )
        errors = contract_errors(bad, plan_with("hook", "payoff"))
        self.assertTrue(any("do not render <SceneShell>" in error for error in errors), errors)
        self.assertTrue(any("do not render <KineticHeading>" in error for error in errors), errors)

    def test_rejects_hardcoded_hex_colors(self):
        for snippet in (
            'const c = "#FFFFFF";\n' + GOOD,
            'const c = "#fff";\n' + GOOD,
            'const c = "#1A1A1Aff";\n' + GOOD,
        ):
            errors = contract_errors(snippet, plan_with("hook", "payoff"))
            self.assertTrue(any("hex color" in error for error in errors), snippet)

    def test_allows_token_based_style(self):
        self.assertEqual(contract_errors(GOOD, plan_with("hook", "payoff")), [])

    def test_scene_key_parser_finds_members(self):
        self.assertEqual(_scene_keys(GOOD), ["hook", "payoff"])


class FenceStripTests(unittest.TestCase):
    def test_strips_fences(self):
        self.assertEqual(strip_fences("```tsx\nconst x = 1;\n```"), "const x = 1;")

    def test_passes_plain_code_through(self):
        self.assertEqual(strip_fences("const x = 1;"), "const x = 1;")


class NormalizeImportsTests(unittest.TestCase):
    def test_fixes_the_components_near_miss(self):
        for wrong, right in (
            ('import { useTheme } from "../../components/lib/theme";',
             'import { useTheme } from "../../lib/theme";'),
            ('import { stylePacks } from "../../components/packs/editorial-ink";',
             'import { stylePacks } from "../../packs/editorial-ink";'),
        ):
            fixed, changed = normalize_imports(wrong)
            self.assertEqual(fixed, right)
            self.assertTrue(changed)

    def test_leaves_correct_paths_alone(self):
        source = 'import { SceneShell } from "../../components/foundation/SceneShell";'
        fixed, changed = normalize_imports(source)
        self.assertEqual(fixed, source)
        self.assertFalse(changed)


class NormalizeTypeTests(unittest.TestCase):
    def test_react19_jsx_element_becomes_an_imported_type(self):
        fixed, changed = normalize_types("const rows: JSX.Element[] = [];")
        self.assertTrue(changed)
        self.assertIn('import type { ReactElement } from "react";', fixed)
        self.assertIn("ReactElement[]", fixed)

    def test_existing_react_element_import_is_reused(self):
        source = 'import type { ReactElement } from "react";\nconst rows: JSX.Element[] = [];'
        fixed, changed = normalize_types(source)
        self.assertTrue(changed)
        self.assertEqual(fixed.count("ReactElement"), 2)
        self.assertNotIn('import type { ReactElement } from "react";\nimport', fixed)

    def test_no_jsx_types_is_a_noop(self):
        source = "const rows: string[] = [];"
        self.assertEqual(normalize_types(source), (source, False))


class LegibilityTests(unittest.TestCase):
    """Pixel gates: blank frames, light-on-paper, dark-on-night."""

    SCENES = {
        "paper": Scene("b", "B", "body", "paper", 4.0, 120),
        "night": Scene("o", "O", "open", "night", 2.67, 80),
    }

    def stats(self, ymin, ymax, yavg, ylow, yhigh):
        return {"YMIN": ymin, "YMAX": ymax, "YAVG": yavg, "YLOW": ylow, "YHIGH": yhigh}

    def issues(self, surface, stats):
        return _legibility_issues(self.SCENES[surface], stats)

    def test_blank_frame_is_flagged(self):
        self.assertTrue(any("blank" in issue for issue in self.issues("paper", self.stats(216, 216, 216, 216, 216))))

    def test_light_on_paper_is_flagged(self):
        self.assertTrue(any("paper" in issue for issue in self.issues("paper", self.stats(38, 235, 208, 199, 215))))

    def test_dark_on_paper_passes(self):
        self.assertEqual(self.issues("paper", self.stats(30, 216, 120, 40, 200)), [])

    def test_dark_night_frame_is_flagged(self):
        self.assertTrue(any("night" in issue for issue in self.issues("night", self.stats(25, 60, 40, 28, 55))))

    def test_bright_on_night_passes(self):
        self.assertEqual(self.issues("night", self.stats(31, 235, 42, 32, 32)), [])


class TypecheckScopeTests(unittest.TestCase):
    def run_tsc(self, output: str):
        completed = mock.Mock(returncode=1, stdout=output, stderr="")
        with mock.patch("vga.codegen.subprocess.run", return_value=completed):
            return typecheck("current")

    def test_errors_in_other_generated_projects_do_not_block(self):
        self.assertEqual(self.run_tsc("src/generated/old/scenes.tsx(1,1): error TS1: bad"), [])

    def test_errors_in_this_project_are_returned(self):
        output = (
            "src/generated/current/scenes.tsx(2,1): error TS1: bad\n"
            "src/generated/old/scenes.tsx(1,1): error TS1: old"
        )
        self.assertEqual(self.run_tsc(output), ["src/generated/current/scenes.tsx(2,1): error TS1: bad"])

    def test_environment_errors_abort_the_repair_loop(self):
        with self.assertRaises(InfraError):
            self.run_tsc("tsconfig.json(1,1): error TS5: bad config")


class EntryTemplateTests(unittest.TestCase):
    def test_entry_sequences_every_scene_in_order(self):
        plan = plan_with("hook", "payoff")
        path = write_entry(board_of(plan))
        text = path.read_text(encoding="utf-8")
        self.assertIn('id: "hook", frames: 90', text)
        self.assertIn('id: "payoff", frames: 90', text)
        self.assertIn("durationInFrames={180}", text)
        self.assertIn('setActivePack("editorial-ink")', text)
        path.unlink()
        path.parent.rmdir()


class FillTests(unittest.TestCase):
    def test_empty_lower_third_is_repaired(self):
        scene = Scene("b", "B", "body", "paper", 4.0, 120)
        issues = _fill_issues(scene, 0.005)
        self.assertTrue(any("lower third" in issue for issue in issues), issues)

    def test_a_label_or_line_is_enough(self):
        scene = Scene("b", "B", "body", "paper", 4.0, 120)
        self.assertEqual(_fill_issues(scene, 0.05), [])
        self.assertEqual(_fill_issues(scene, None), [])


class MotionTests(unittest.TestCase):
    def test_static_hold_is_repaired(self):
        scene = Scene("b", "B", "body", "paper", 4.0, 120)
        issues = _motion_issues(scene, 0.01)
        self.assertTrue(any("static" in issue for issue in issues), issues)
        self.assertTrue(any("Alive" in issue for issue in issues), issues)

    def test_alive_enough_passes(self):
        scene = Scene("b", "B", "body", "paper", 4.0, 120)
        self.assertEqual(_motion_issues(scene, 2.5), [])
        self.assertEqual(_motion_issues(scene, None), [])


class MediaLegibilityTests(unittest.TestCase):
    def stats(self, ymin, ymax, yavg, ylow, yhigh):
        return {"YMIN": ymin, "YMAX": ymax, "YAVG": yavg, "YLOW": ylow, "YHIGH": yhigh}

    def test_media_scene_skips_surface_color_rules(self):
        from vga.models import Scene

        scene = Scene("m", "M", "body", "paper", 4.0, 120, "tweet-1")
        # ymax 250 would be "near-white on paper" for a drawn scene; a photo is exempt.
        self.assertEqual(_legibility_issues(scene, self.stats(38, 250, 210, 199, 215)), [])

    def test_media_scene_still_flags_blank(self):
        from vga.models import Scene

        scene = Scene("m", "M", "body", "night", 4.0, 120, "tweet-1")
        issues = _legibility_issues(scene, self.stats(14, 16, 15, 14, 16))
        self.assertTrue(any("blank" in issue for issue in issues))


if __name__ == "__main__":
    unittest.main()


