"""Plan stage: one LLM call turns a prompt into scene structure.

The model proposes content (titles, look, pacing weights). The structure is
enforced here, not trusted: ids are sanitized, surfaces alternate out of night,
kinds are positional (open / body / close), scene counts are inside the feasible
window, and the pacing weights resolve to exact seconds later.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .assets import Asset, brief_lines
from .duration import scene_count_range
from .llm import LlmConfig, chat_json
from .models import RESERVED_SCENE_IDS, SCENE_ID_RE
from .prompts import PLAN_SYSTEM

MAX_TITLE_CHARS = 42


@dataclass
class PlannedScene:
    id: str
    title: str
    kind: str
    surface: str
    weight: float
    asset: str | None = None
    visual: str = ""
    layout: str = "canvas"
    motion: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Plan:
    idea: str
    target: float
    title: str
    angle: str
    audience: str
    scenes: list[PlannedScene]
    research: dict = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "idea": self.idea,
            "target": self.target,
            "title": self.title,
            "angle": self.angle,
            "audience": self.audience,
            "scenes": [scene.to_dict() for scene in self.scenes],
            "research": self.research,
        }


def make_plan(idea: str, target: float, assets: list[Asset], llm: LlmConfig, research: dict | None = None) -> Plan:
    from .research import research_brief

    low, high = scene_count_range(target)
    asset_ids = frozenset(asset.id for asset in assets)
    asset_block = asset_brief(assets)
    messages = [
        {"role": "system", "content": PLAN_SYSTEM},
        {
            "role": "user",
            "content": f"""Idea: {idea}
Target length: {target:g} seconds, in one hard gate (never estimated).

Between {low} and {high} scenes. First scene opens, last scene closes.

{asset_block}

{research_brief(research or {})}

Return JSON:
{{
  "title": "<video title, under 8 words>",
  "angle": "<the single mechanism this explains, 15-25 words>",
  "audience": "<who this is for, concretely>",
  "scenes": [
    {{"title": "<what this scene says/asks, uppercase, max 7 words>",
      "surface": "paper" or "night",
      "layout": "canvas" (bespoke UI/object composition), "diagram" (fixed header), "card" or "media",
      "visual": "<what the viewer SEES, 10-30 words: one concrete subject-specific picture, UI interaction, or animation. Specify composition, what changes, and its visible outcome; vary framing across scenes.>",
      "motion": {{"start": "<concrete initial visible state>", "action": "<specific state-changing animation, not idle drift>", "end": "<visible completed outcome reached by 75% of the scene; hold it legibly>"}},
      "weight": <scene length hint in seconds, 2-5, real number>,
      "asset": "<asset id, only when you anchor this scene on it; omit otherwise>"}}
  ]
}}""",
        },
    ]

    def validate(data: Any) -> dict:
        if not isinstance(data, dict):
            raise ValueError("plan: response must be a JSON object")
        _require(data, "title", str)
        _require(data, "angle", str)
        _require(data, "audience", str)
        scenes = _require(data, "scenes", list)
        if not low <= len(scenes) <= high:
            raise ValueError(f"plan: {len(scenes)} scenes, need {low}-{high} for a {target:g}s video")
        for scene in scenes:
            _require(scene, "title", str)
            _require(scene, "visual", str)
            _require(scene, "weight", int, float)
            if scene.get("layout", "canvas") not in ("canvas", "diagram", "card", "media"):
                raise ValueError("plan: invalid layout")
            if "motion" in scene:
                motion = scene["motion"]
                if (not isinstance(motion, dict) or set(motion) != {"start", "action", "end"}
                        or any(not isinstance(value, str) or not 1 <= len(value.strip()) <= 240
                               for value in motion.values())):
                    raise ValueError("plan: motion needs exactly start/action/end strings of 1-240 characters")
            if surface_test(scene):
                raise ValueError("plan: surface must be \"paper\" or \"night\"")
            asset = scene.get("asset")
            if asset is not None:
                if not isinstance(asset, str) or asset not in asset_ids:
                    raise ValueError(
                        f"plan: scene asset must be one of the provided asset ids "
                        f"{sorted(asset_ids) if asset_ids else '(none provided — omit the asset field)'}"
                    )
        return data

    data = chat_json(llm, messages, validate, stage="plan")
    plan = Plan(
        idea=idea,
        target=target,
        title=data["title"].strip(),
        angle=data["angle"].strip(),
        audience=data["audience"].strip(),
        scenes=[],
        research=research or {},
    )
    plan.scenes = build_scenes(data["scenes"])
    repair_plan(plan, asset_ids)
    assets_by_id = {asset.id: asset for asset in assets}
    for scene in plan.scenes:
        if scene.asset:
            scene.layout = "media" if assets_by_id[scene.asset].file else "diagram"
    return plan


def asset_brief(assets: list[Asset]) -> str:
    if not assets:
        return (
            "No media assets are provided. Every scene is drawn animation — omit the "
            '"asset" field everywhere. This is a perfectly good video shape.'
        )
    return (
        "Media assets are available. Anchoring a scene on one makes the video feel "
        "current and real: the artifact is the proof, your job is the explanation.\n"
        f"Rules: put \"asset\" on a scene only for these exact ids; prefer an animated "
        "image when it directly demonstrates the mechanism; at most one media "
        "scene per three; open and close scenes stay cards unless an asset truly is "
        "the star; never anchor two scenes on the same asset; any number of media "
        "scenes (even none) is fine when the story is stronger without them.\n"
        + brief_lines(assets)
    )


def clip_title(value: str, limit: int = MAX_TITLE_CHARS) -> str:
    """Uppercase, at most `limit` chars, cut on a word boundary.

    A hard slice shipped titles like "SHIPPING HAPPE"; a trailing ellipsis is
    honest and still fits the preflight length contract.
    """
    title = value.strip().upper()
    if len(title) <= limit:
        return title
    cut = title[: limit - 1]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut.rstrip(" ,;:-") + "…"


def surface_test(scene: dict) -> bool:
    return not isinstance(scene.get("surface"), str) or scene["surface"] not in ("paper", "night")


def _require(data: dict, key: str, *kinds: type, where: str = "plan") -> Any:
    if not isinstance(data, dict):
        raise ValueError(f"{where}: expected a JSON object")
    value = data.get(key)
    if value is None:
        raise ValueError(f"{where}: missing {key}")
    if kinds and not isinstance(value, kinds):
        raise ValueError(f"{where}: {key} must be {' or '.join(kind.__name__ for kind in kinds)}")
    return value


def build_scenes(raw: list[dict]) -> list[PlannedScene]:
    scenes: list[PlannedScene] = []
    for index, item in enumerate(raw):
        asset = item.get("asset")
        scene = PlannedScene(
            id=f"scene{index + 1:02d}",
            title=clip_title(str(item.get("title", ""))),
            kind="body",
            surface=str(item.get("surface") or "paper"),
            visual=str(item.get("visual") or "").strip(),
            layout=str(item.get("layout") or "canvas"),
            motion={key: value.strip() for key, value in item.get("motion", {}).items()},
            weight=float(item.get("weight") or 0),
            asset=str(asset) if asset else None,
        )
        scenes.append(scene)
    return scenes


def repair_plan(plan: Plan, asset_ids: frozenset[str] = frozenset()) -> None:
    """Enforce the invariants the model is asked for but cannot be trusted with."""
    scenes = plan.scenes
    low, high = scene_count_range(plan.target)
    if not low <= len(scenes) <= high:
        raise ValueError(f"Plan has {len(scenes)} scenes; feasible count is {low}-{high} for {plan.target:g}s.")

    seen_assets: set[str] = set()
    for index, scene in enumerate(scenes):
        if not SCENE_ID_RE.match(scene.id):
            scene.id = f"scene{index + 1:02d}"
        while scene.id in RESERVED_SCENE_IDS:
            scene.id = f"{scene.id}_"
        scene.surface = "night" if scene.surface == "night" else "paper"
        if not scene.title:
            scene.title = f"SCENE {index + 1}"
        scene.kind = "open" if index == 0 else ("close" if index == len(scenes) - 1 else "body")
        # An asset only exists if it was provided, and is spent once.
        if scene.asset not in asset_ids or scene.asset in seen_assets:
            scene.asset = None
        else:
            seen_assets.add(scene.asset)
        if scene.asset is None and scene.layout == "media":
            scene.layout = "canvas"

    # The open and close cards may be night; body scenes must not stack night.
    for previous, current in zip(scenes, scenes[1:]):
        if previous.surface == "night" and current.surface == "night":
            current.surface = "paper"
