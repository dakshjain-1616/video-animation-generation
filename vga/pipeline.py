"""Orchestrator: deterministic stages, artifacts on disk, one hard duration gate.

prompt -> plan (LLM) -> timed storyboard -> scene code (LLM, checked)
       -> preflight -> render -> duration report + QA
"""

from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import replace
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path

from .assets import Asset, load_assets, stage_assets
from .codegen import generate_scenes, write_entry
from .collect import collect_media
from .research import research_visuals
from .duration import allocate_frames, planned_target, resolve_durations
from .llm import (
    ProviderNotConfigured,
    reset_usage,
    resolve_llm_config,
    set_usage_sink,
    stage_config,
    usage_summary,
)
from .models import DEFAULT_ASPECT, FORMATS, Scene, Storyboard, duration_pass
from .plan import make_plan
from .preflight import preflight
from . import music as soundtrack
from . import voice as voiceover
from .render import REPO_ROOT, render_stills, render_storyboard

PROJECTS = REPO_ROOT / "data" / "projects"

MIN_IDEA_CHARS = 8
# Kept in sync with src/packs/registry.ts (adding a pack is one file + this line).
PACK_IDS = ("editorial-ink", "clinical-slate", "sunset-paper", "forest-ink", "mono-graphite")


def project_dir(project_id: str) -> Path:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,47}", project_id):
        raise ValueError("project id must use lowercase letters, digits and dashes (max 48 characters)")
    return PROJECTS / project_id


def _run_project(
    project_id: str,
    idea: str,
    target: float = 30.0,
    category: str = "explainer",
    pack: str | None = None,
    assets: list[Asset] | None = None,
    fetch_media: bool = False,
    aspect: str = DEFAULT_ASPECT,
    voice: bool = False,
    voice_id: str | None = None,
    review: bool = True,
    music: str | None = None,
    log=print,
    web_research: bool = True,
) -> dict:
    assets = list(assets or [])
    pack = pack or os.environ.get("VGA_PACK") or "editorial-ink"
    llm = resolve_llm_config()
    if llm is None:
        raise ProviderNotConfigured(
            "No LLM key. Put OPENROUTER_API_KEY in .env (or set OPENAI_API_KEY / "
            "VGA_LLM_API_KEY + VGA_LLM_BASE_URL + VGA_LLM_MODEL). Run `python -m vga doctor`."
        )
    if category != "explainer":
        raise ValueError(f'Unknown category "{category}". This tool ships the "explainer" category.')
    if pack not in PACK_IDS:
        raise ValueError(f'Unknown pack "{pack}". Available: {", ".join(PACK_IDS)}.')
    if aspect not in FORMATS:
        raise ValueError(f'Unknown aspect "{aspect}". Available: {", ".join(FORMATS)}.')
    if voice and not voiceover.api_key():
        raise ValueError("--voice needs ELEVENLABS_API_KEY in .env (run `python -m vga doctor`).")
    if not target_in_window(target):
        raise ValueError(f"Target {target:g}s is outside the 20-60s platform window.")
    idea = idea.strip()
    if len(idea) < MIN_IDEA_CHARS:
        raise ValueError(f"Give a real prompt: at least {MIN_IDEA_CHARS} characters.")
    # Quality/cost routing: only the stages that need the strongest model pay
    # for it. The default remains one model for everything.
    plan_llm = stage_config(llm, "VGA_PLAN_MODEL")
    code_llm = replace(
        stage_config(llm, "VGA_CODEGEN_MODEL"),
        max_tokens=_codegen_token_budget(),
    )
    review_llm = stage_config(llm, "VGA_REVIEW_MODEL")
    codegen_attempts = _codegen_attempts()
    # Resolve the music choice before spending a single LLM call: a missing or
    # unreadable track is a caller error, not something to discover after render.
    music_request = soundtrack.resolve_request(music, pack)

    directory = project_dir(project_id)
    directory.mkdir(parents=True, exist_ok=True)
    _clear_run_outputs(directory)
    run_record = {
        "schemaVersion": 1,
        "status": "running",
        "startedAt": datetime.now(timezone.utc).isoformat(),
        "events": [],
    }

    def save_run() -> None:
        _write(directory / "run.json", run_record)

    save_run()

    last_event_at = datetime.now(timezone.utc)

    def event(stage: str, data: dict | None = None) -> None:
        nonlocal last_event_at
        now = datetime.now(timezone.utc)
        entry = {
            "at": now.isoformat(),
            "stage": stage,
            "elapsed": round((now - last_event_at).total_seconds(), 3),
            **(data or {}),
        }
        last_event_at = now
        run_record["activeStage"] = stage
        run_record["events"].append(entry)
        save_run()

    # Reset the token ledger before any LLM stage (collect included) so
    # Keep usage in the same incremental run record, including on mid-run errors.
    reset_usage()
    def record_usage(usage: dict) -> None:
        run_record["usage"] = usage
        save_run()
    set_usage_sink(record_usage)

    run_record["activeStage"] = "research"
    save_run()
    research = research_visuals(directory, idea, plan_llm, log=log, persist=False) if web_research else {"status": "disabled", "sources": []}
    run_record["research"] = research
    save_run()
    event("research", {"status": research["status"], "sources": len(research.get("sources", []))})

    # 0. Fetch media (opt-in): search + download relevant images/clips.
    if fetch_media:
        run_record["activeStage"] = "collect"
        save_run()
        collected = collect_media(directory, idea, llm, log=log)
        if collected:
            known = {asset.id for asset in assets}
            for asset in collected:
                if asset.id in known:
                    continue
                assets.append(asset)
            event("collect", {"count": len(collected)})

    # 1. Plan
    run_record["activeStage"] = "plan"
    save_run()
    log(f'[plan] "{idea}" -> {target:g}s ({category}, pack {pack}, {aspect}{", voice" if voice else ""})')
    plan = make_plan(idea, target, assets, plan_llm, research=research)
    run_record["plan"] = {key: value for key, value in plan.to_dict().items() if key != "research"}
    save_run()
    media_scenes = [scene.id for scene in plan.scenes if scene.asset]
    log(
        f"[plan] {plan.title}: {len(plan.scenes)} scenes"
        + (f", media on {', '.join(media_scenes)}" if media_scenes else ", all animation")
        + f", angle: {plan.angle}"
    )

    # 2. Timed storyboard (frames resolve from plan weights, exactly to target)
    seconds = resolve_durations([scene.weight for scene in plan.scenes], planned_target(target))
    frames = allocate_frames(seconds, 30)
    storyboard = Storyboard(
        id=project_id,
        title=plan.title,
        category="explainer",  # type: ignore[arg-type]
        pack=pack,
        target=planned_target(target),
        fps=30,
        width=FORMATS[aspect][0],
        height=FORMATS[aspect][1],
        entry=f"src/generated/{project_id}/entry.tsx",
        scenes=[
            Scene(
                id=plan_scene.id,
                title=plan_scene.title,
                kind=plan_scene.kind,  # type: ignore[arg-type]
                surface=plan_scene.surface,  # type: ignore[arg-type]
                seconds=seconds[i],
                frames=frames[i],
                asset=plan_scene.asset,
            )
            for i, plan_scene in enumerate(plan.scenes)
        ],
    )
    storyboard_target = storyboard.target
    storyboard.write(str(directory / "storyboard.json"))
    write_entry(storyboard)  # deterministic plumbing; scenes.tsx lands next to it below
    event("storyboard", {"scenes": len(storyboard.scenes), "frames": storyboard.frames()})
    log(
        f"[storyboard] {storyboard.seconds():.2f}s planned, {storyboard.frames()} frames @ 30fps"
    )

    # 2.2 Voice-over (opt-in): script per scene, speech, one scene-aligned track.
    voice_track = None
    if voice:
        run_record["activeStage"] = "voice"
        save_run()
        script = voiceover.write_script(storyboard, plan, llm)
        for scene, line in zip(storyboard.scenes, script):
            scene.narration = line
        storyboard.write(str(directory / "storyboard.json"))
        voice_track = voiceover.build_track(
            storyboard, script, directory, voice_id or os.environ.get("VGA_VOICE_ID", voiceover.DEFAULT_VOICE_ID),
            voiceover.api_key(),
        )
        event("voice", {"scenes": len(script), "track": str(voice_track.relative_to(directory))})
        log(f"[voice] {len(script)} lines synthesized -> {voice_track.relative_to(directory)}")

    # 2.3 Music (opt-in) and one mixed audio track. The mix is built after the
    # voice so the bed can duck under it; it is exactly the video length.
    music_track = None
    if music_request is not None:
        run_record["activeStage"] = "music"
        save_run()
        music_track = soundtrack.build_bed(music_request, storyboard, directory)
        label = music_request.file.name if music_request.file else "generated cue"
        event("music", {"source": music_request.source, "bed": str(music_track.relative_to(directory))})
        log(f"[music] {label} -> {music_track.relative_to(directory)}")
    mix = soundtrack.build_mix(storyboard, directory, voice_track, music_track)
    if mix is not None:
        run_record["audio"] = (
            soundtrack.metadata(music_request, storyboard, music_track, mix, voice)
            if music_request is not None
            else {"source": "voice-only", "voice": True, "mix": str(mix.relative_to(directory))}
        )
        save_run()
        event("audio", {"mix": str(mix.relative_to(directory)), "music": music_request is not None})
        log(f"[audio] mixed -> {mix.relative_to(directory)}")

    # 2.5 Assets onto disk: public/generated/<id>/ for the bundler, and a
    # caller-facing copy in the project directory.
    if assets:
        asset_dir = directory / "assets"
        asset_dir.mkdir(parents=True, exist_ok=True)
        for asset in assets:
            if asset.file:
                stored_file = asset_dir / f"{asset.id}{Path(asset.file).suffix.lower()}"
                shutil.copyfile(asset.file, stored_file)
                asset.file = str(stored_file)
        stage_assets(project_id, assets)
        _write(directory / "assets.json", [asset.to_dict() for asset in assets])
        shutil.rmtree(directory / "assets-src", ignore_errors=True)
        event("assets", {"staged": [asset.staged for asset in assets if asset.staged]})
        staged_count = len([asset for asset in assets if asset.staged])
        log(f"[assets] {len(assets)} total, {staged_count} file(s) staged into public/")

    # 3. Scene code (static checks + typecheck + stills legibility, repaired with feedback)
    run_record["activeStage"] = "codegen"
    save_run()
    def record_attempts(rows: list[dict]) -> None:
        run_record["codeAttempts"] = rows
        save_run()

    code_report = generate_scenes(
        storyboard,
        plan,
        code_llm,
        assets=assets,
        attempts=codegen_attempts,
        review=review,
        review_llm=review_llm,
        diagnostics_sink=record_attempts,
    )
    run_record["codegen"] = code_report
    save_run()
    event("codegen", {"attempts": code_report["attempts"]})
    log(f"[codegen] scenes.tsx written (attempt {code_report['attempts']})")

    # 4. Preflight
    run_record["activeStage"] = "preflight"
    save_run()
    checks = preflight(plan, storyboard, code_report, assets=assets)
    run_record["preflight"] = checks
    save_run()
    if not checks["pass"]:
        event("preflight-failed", {"errors": checks["errors"]})
        raise ValueError("Preflight failed:\n- " + "\n- ".join(checks["errors"]))
    log(f"[preflight] pass ({len(checks['warnings'])} note(s))")

    # 5. Render (Node service) + hard duration gate
    run_record["activeStage"] = "render"
    save_run()
    result = render_storyboard(
        str(directory / "storyboard.json"),
        str(directory / "render" / "final.mp4"),
    )
    result = _attach_audio(directory, result)
    event(
        "render",
        {
            k: result[k]
            for k in ("actual", "target", "delta", "pass", "renderSeconds", "sizeBytes")
            if k in result
        },
    )
    log(
        f"[render] target {result['target']:.2f}s · actual {result['actual']:.2f}s · "
        f"{result['delta']:+.2f}s {'PASS' if result['pass'] else 'FAIL'}"
    )

    # 6. Duration report + QA summary
    duration = {
        "target": target,
        "planned": storyboard_target,
        "actual": round(result["actual"], 3),
        "delta": round(result["delta"], 3),
        "tolerance": 2,
        "pass": duration_pass(result["actual"], target),
        "frames": result["frames"],
        "fps": storyboard.fps,
        "renderSeconds": result.get("renderSeconds"),
        "sizeBytes": result.get("sizeBytes"),
        "file": str((directory / "render" / "final.mp4").relative_to(REPO_ROOT)),
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    }
    run_record["duration"] = duration

    # A critique the art director raised on the final repair attempt is not
    # cosmetic bookkeeping: the video still renders, but the run is not clean.
    unresolved = [
        note.removeprefix("unresolved review: ")
        for note in code_report.get("notes", [])
        if note.startswith("unresolved review:")
    ]
    qa = {
        "pass": checks["pass"] and duration["pass"] and not unresolved and (not review or code_report.get("review") == "passed"),
        "duration": duration["pass"],
        "preflight": checks["pass"],
        "reviewUnresolved": unresolved,
        "codeAttempts": code_report["attempts"],
        "review": code_report.get("review", "unknown"),
        "research": research["status"],
        "notes": [],
    }
    if not duration["pass"]:
        qa["notes"].append(f"duration {duration['delta']:+.2f}s outside the ±2s gate")
    if review and qa["review"] != "passed":
        qa["notes"].append(f"vision review {qa['review']}; visual quality is not verified")
    qa["notes"].extend(unresolved)
    run_record["qa"] = qa
    log(f"[qa] {'PASS' if qa['pass'] else 'FAIL'}" + (f" ({qa['notes'][0]})" if qa["notes"] else ""))

    # Usage accounting: tokens and estimated cost for this run's LLM calls.
    summary = usage_summary()
    run_record["usage"] = {"model": llm.model, **summary}
    run_record["status"] = "complete" if qa["pass"] else "failed"
    run_record["activeStage"] = None
    run_record["finishedAt"] = datetime.now(timezone.utc).isoformat()
    save_run()
    if qa["pass"]:
        shutil.rmtree(directory / "qa" / "visual", ignore_errors=True)
    estimate = summary["estimated_usd"]
    log(
        f"[usage] {summary['calls']} calls · {summary['input_tokens']} in / {summary['output_tokens']} out tok"
        + (f" · ≈${estimate:.4f}" if estimate is not None else "")
    )

    return _summary(directory, storyboard, qa, duration)


@wraps(_run_project)
def run_project(*args, **kwargs) -> dict:
    """Mark interrupted stages clearly and always detach the run's usage sink."""
    project_id = kwargs.get("project_id") or (args[0] if args else None)
    started_at = datetime.now(timezone.utc)
    try:
        return _run_project(*args, **kwargs)
    except Exception as error:
        if isinstance(project_id, str):
            _mark_run_failed(project_id, started_at, error)
        raise
    finally:
        set_usage_sink(None)


def _mark_run_failed(project_id: str, started_at: datetime, error: Exception) -> None:
    try:
        path = project_dir(project_id) / "run.json"
    except ValueError:
        return
    record = _read_json(path)
    if not record or record.get("status") != "running":
        return
    try:
        run_started_at = datetime.fromisoformat(record.get("startedAt", ""))
    except (TypeError, ValueError):
        return
    if run_started_at.tzinfo is None:
        run_started_at = run_started_at.replace(tzinfo=timezone.utc)
    if run_started_at < started_at:
        return
    record["status"] = "failed"
    record["error"] = {"stage": record.get("activeStage"), "message": str(error)[:1000]}
    record["activeStage"] = None
    record["finishedAt"] = datetime.now(timezone.utc).isoformat()
    _write(path, record)


def render_from_disk(project_id: str, out: str | None = None, crf: int | None = None) -> dict:
    directory = project_dir(project_id)
    storyboard_path = directory / "storyboard.json"
    if not storyboard_path.exists():
        raise FileNotFoundError(f"No storyboard for project {project_id}")
    result = render_storyboard(str(storyboard_path), out or str(directory / "render" / "final.mp4"), crf)
    if out is None:
        result = _attach_audio(directory, result)
    return _summary(directory, _load_board(str(storyboard_path)), None, result)


def stills_from_disk(project_id: str, frames: list[int]) -> list[str]:
    directory = project_dir(project_id)
    storyboard_path = directory / "storyboard.json"
    if not storyboard_path.exists():
        raise FileNotFoundError(f"No storyboard for project {project_id}")
    return render_stills(str(storyboard_path), frames, str(directory / "qa" / "frames"))


def _attach_audio(directory: Path, result: dict) -> dict:
    """Mux the project's mixed audio (voice and/or music) under the video."""
    track = directory / "audio" / "mix.m4a"
    if not track.exists():
        legacy = directory / "voice" / "voice.m4a"
        if not legacy.exists():
            return result
        track = legacy
    actual = soundtrack.mux(directory / "render" / "final.mp4", track)
    return {**result, "actual": actual, "delta": actual - result["target"],
            "pass": duration_pass(actual, result["target"])}


def _load_board(path: str) -> Storyboard:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return Storyboard(
        id=data["id"],
        title=data["title"],
        category=data["category"],
        target=data["target"],
        fps=data["fps"],
        width=data["width"],
        height=data["height"],
        entry=data["entry"],
        pack=data.get("pack"),
        scenes=[_scene_from(s) for s in data["scenes"]],
    )


def _scene_from(data: dict) -> Scene:
    return Scene(
        id=data["id"],
        title=data["title"],
        kind=data["kind"],
        surface=data["surface"],
        seconds=data["seconds"],
        frames=data["frames"],
        asset=data.get("asset"),
        narration=data.get("narration"),
    )


def _summary(directory: Path, storyboard: Storyboard | None, qa: dict | None, result: dict) -> dict:
    duration = {
        "actual": result["actual"],
        "target": result["target"],
        "delta": result["delta"],
        "pass": duration_pass(result["actual"], result["target"]),
    }
    return {
        "dir": str(directory),
        "storyboard": storyboard,
        "qa": qa,
        "duration": duration,
        "video": str(directory / "render" / "final.mp4") if duration["pass"] else None,
    }


def _clear_run_outputs(directory: Path) -> None:
    """Remove audio and gate artifacts before a re-run.

    A previous run's voice/music mix or final.mp4 must never be silently
    attached to, or mistaken for, this run's output.
    """
    for folder in ("voice", "music", "audio", "assets", "assets-src", "qa", "code"):
        shutil.rmtree(directory / folder, ignore_errors=True)
    for file in (
        "run.json", "plan.json", "research.json", "code-attempts.json", "codegen.json", "assets.json", "storyboard.json",
        "preflight.json", "duration.json", "qa.json", "audio.json", "usage.json",
        "events.jsonl",
    ):
        (directory / file).unlink(missing_ok=True)
    (directory / "render" / "final.mp4").unlink(missing_ok=True)
    shutil.rmtree(REPO_ROOT / "src" / "generated" / directory.name, ignore_errors=True)
    shutil.rmtree(REPO_ROOT / "public" / "generated" / directory.name, ignore_errors=True)


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _codegen_token_budget(default: int = 32_000) -> int:
    """Output-token budget for scene code; 8-10 scenes can exceed 16k."""
    raw = os.environ.get("VGA_CODEGEN_MAX_TOKENS")
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as error:
        raise ValueError("VGA_CODEGEN_MAX_TOKENS must be an integer between 4096 and 64000") from error
    if not 4096 <= value <= 64_000:
        raise ValueError("VGA_CODEGEN_MAX_TOKENS must be between 4096 and 64000")
    return value


def _codegen_attempts(default: int = 4) -> int:
    """Repair budget, overridable for a quality pass (1-6 attempts)."""
    raw = os.environ.get("VGA_CODEGEN_ATTEMPTS")
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as error:
        raise ValueError("VGA_CODEGEN_ATTEMPTS must be an integer between 1 and 6") from error
    if not 1 <= value <= 6:
        raise ValueError("VGA_CODEGEN_ATTEMPTS must be between 1 and 6")
    return value


def target_in_window(target: float) -> bool:
    # 20 <= target <= 60, hard bounds; float noise tolerated by fractions of a ms.
    return 20.0 - 1e-9 <= target <= 60.0 + 1e-9


def list_projects() -> list[dict]:
    if not PROJECTS.exists():
        return []
    projects = []
    for directory in sorted(PROJECTS.iterdir()):
        if not directory.is_dir():
            continue
        run = _read_json(directory / "run.json") or {}
        qa = run.get("qa") or _read_json(directory / "qa.json")
        duration = run.get("duration") or _read_json(directory / "duration.json")
        plan = run.get("plan") or _read_json(directory / "plan.json")
        projects.append(
            {
                "id": directory.name,
                "title": (plan or {}).get("title"),
                "target": (duration or {}).get("target"),
                "duration": (duration or {}).get("actual"),
                "pass": (qa or {}).get("pass"),
            }
        )
    return projects


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def load_plan(project_id: str) -> dict | None:
    run = _read_json(project_dir(project_id) / "run.json") or {}
    return run.get("plan") or _read_json(project_dir(project_id) / "plan.json")


def load_storyboard(project_id: str) -> dict | None:
    return _read_json(project_dir(project_id) / "storyboard.json")
