import json
import shutil
import tempfile
import unittest
from pathlib import Path

from vga.assets import Asset, load_assets, stage_assets
from vga.plan import Plan, PlannedScene, repair_plan
from vga.preflight import preflight


class TempDir(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)

    def write(self, name: str, data: bytes) -> Path:
        path = self.tmp / name
        path.write_bytes(data)
        return path


class LoadAssetsTests(TempDir):
    def manifest(self, entries: list[dict], file_name: str = "tweet-1.png") -> dict:
        image = self.write(file_name, b"fake png")
        for entry in entries:
            if entry.get("file") == file_name:
                entry["file"] = str(image)
        return entries

    def test_roundtrip_and_resolution(self):
        entries = self.manifest(
            [
                {
                    "id": "tweet-1",
                    "kind": "tweet",
                    "file": "tweet-1.png",
                    "caption": "@ada",
                    "source": "X",
                },
                {"id": "headline-1", "kind": "news", "content": "Rates held steady", "source": "Reuters"},
            ]
        )
        manifest = self.tmp / "assets.json"
        manifest.write_text(json.dumps(entries), encoding="utf-8")
        assets = load_assets(str(manifest))
        self.assertEqual([asset.id for asset in assets], ["tweet-1", "headline-1"])
        self.assertTrue(assets[0].file.endswith("tweet-1.png"))
        self.assertIsNone(assets[1].file)
        self.assertEqual(assets[1].content, "Rates held steady")

    def test_rejects_bad_manifests(self):
        cases = {
            "unknown kind": [{"id": "a", "kind": "meme", "content": "x"}],
            "duplicate id": [
                {"id": "a", "kind": "tweet", "content": "x"},
                {"id": "a", "kind": "news", "content": "y"},
            ],
            "clip without file": [{"id": "c", "kind": "clip"}],
            "missing file": [{"id": "a", "kind": "tweet", "file": "nope.png"}],
            "no file no content": [{"id": "a", "kind": "tweet"}],
            "non-finite start": [{"id": "a", "kind": "clip", "file": "clip.mp4", "startAt": float("nan")}],
            "bad animated flag": [{"id": "a", "kind": "image", "file": "shot.png", "animated": "yes"}],
        }
        for label, entries in cases.items():
            with self.subTest(label):
                manifest = self.tmp / "assets.json"
                manifest.write_text(json.dumps(entries), encoding="utf-8")
                with self.assertRaises(Exception) as caught:
                    load_assets(str(manifest))
                del caught
            (self.tmp / "assets.json").unlink()

    def test_bad_id_rejected(self):
        manifest = self.tmp / "assets.json"
        manifest.write_text(json.dumps([{"id": "bad id", "kind": "tweet", "content": "x"}]), encoding="utf-8")
        with self.assertRaisesRegex(Exception, "asset id"):
            load_assets(str(manifest))

    def test_long_content_truncates(self):
        manifest = self.tmp / "assets.json"
        manifest.write_text(
            json.dumps([{"id": "a", "kind": "tweet", "content": "x" * 3000}]), encoding="utf-8"
        )
        assets = load_assets(str(manifest))
        self.assertLessEqual(len(assets[0].content), 600 + 1)  # + ellipsis


class StageAssetsTests(TempDir):
    def test_copies_files_deterministically(self):
        import vga.assets as assets_module

        image = self.write("shot.png", b"png bytes")
        target_root = self.tmp / "public"
        original = assets_module.PUBLIC_ROOT
        assets_module.PUBLIC_ROOT = target_root
        self.addCleanup(setattr, assets_module, "PUBLIC_ROOT", original)

        asset = Asset(id="tweet-1", kind="tweet", file=str(image))
        stage_assets("proj-x", [asset])
        staged = target_root / "generated" / "proj-x" / "tweet-1.png"
        self.assertTrue(staged.exists())
        self.assertEqual(staged.read_bytes(), b"png bytes")
        self.assertEqual(asset.staged, "generated/proj-x/tweet-1.png")


class PlanAssetRepairTests(unittest.TestCase):
    def plan(self, assets: list[str | None]) -> Plan:
        scenes = [
            PlannedScene(
                f"scene{i + 1:02d}",
                "T",
                "open" if i == 0 else ("close" if i == 5 else "body"),
                "paper",
                3.5,
                assets[i] if i < len(assets) else None,
            )
            for i in range(6)
        ]
        return Plan(idea="i", target=20.0, title="t", angle="a", audience="x", scenes=scenes)

    def test_unknown_asset_dropped(self):
        plan = self.plan(["nope"])
        repair_plan(plan, frozenset({"tweet-1"}))
        self.assertIsNone(plan.scenes[0].asset)

    def test_each_asset_used_once(self):
        plan = self.plan(["tweet-1", "tweet-1"])
        repair_plan(plan, frozenset({"tweet-1"}))
        self.assertEqual([scene.asset for scene in plan.scenes], ["tweet-1", None, None, None, None, None])

    def test_no_assets_clears_everything(self):
        plan = self.plan(["tweet-1"])
        repair_plan(plan)
        self.assertIsNone(plan.scenes[0].asset)


class PreflightAssetTests(TempDir):
    def assets(self, stage: bool, create_file: bool = True) -> list[Asset]:
        import vga.assets as assets_module

        image = self.write("shot.png", b"png")
        public = self.tmp / "public"
        original = assets_module.PUBLIC_ROOT
        assets_module.PUBLIC_ROOT = public
        self.addCleanup(setattr, assets_module, "PUBLIC_ROOT", original)
        if stage and create_file:
            (public / "generated" / "p").mkdir(parents=True)
            (public / "generated" / "p" / "tweet-1.png").write_bytes(b"png")
        return [
            Asset(
                id="tweet-1",
                kind="tweet",
                file=str(image),
                staged="generated/p/tweet-1.png" if stage else None,
            ),
            Asset(id="quote-1", kind="tweet", content="unused quote"),
        ]

    def preflight(self, stage: bool = True, asset: str | None = None, create_file: bool = True) -> dict:
        plan = Plan(idea="i", target=20.0, title="t", angle="a", audience="x", scenes=_plan_scenes(asset))
        board = _board(asset)
        return preflight(
            plan, board, {"pass": True, "attempts": 1}, assets=self.assets(stage, create_file)
        )

    def test_unstaged_file_backed_asset_fails(self):
        report = self.preflight(stage=False)
        self.assertFalse(report["pass"])
        self.assertTrue(any("not staged" in error for error in report["errors"]))

    def test_missing_staged_file_fails_before_render(self):
        report = self.preflight(stage=True, create_file=False)
        self.assertFalse(report["pass"])
        self.assertTrue(any("staged file is missing" in error for error in report["errors"]))

    def test_unknown_scene_asset_fails(self):
        report = self.preflight(asset="ghost")
        self.assertFalse(report["pass"])
        self.assertTrue(any("unknown asset" in error for error in report["errors"]))

    def test_passes_with_unused_note(self):
        report = self.preflight(asset="tweet-1")
        self.assertTrue(report["pass"])
        self.assertTrue(any("quote-1" in note for note in report["warnings"]))


def _plan_scenes(asset: str | None) -> list:
    return [
        PlannedScene(
            f"scene{i + 1:02d}",
            "T",
            "open" if i == 0 else ("close" if i == 5 else "body"),
            "paper",
            3.5,
            asset if i == 0 else None,
        )
        for i in range(6)
    ]


def _board(asset: str | None):
    from vga.models import Scene, Storyboard

    return Storyboard(
        id="p",
        title="t",
        category="explainer",
        pack="editorial-ink",
        target=20.0,
        fps=30,
        width=1920,
        height=1080,
        entry="src/generated/p/entry.tsx",
        scenes=[
            Scene(
                scene.id,
                "T",
                scene.kind,
                "paper",
                3.5,
                105,
                asset if scene.id == "scene01" else None,
            )
            for scene in _plan_scenes(asset)
        ],
    )


if __name__ == "__main__":
    unittest.main()
