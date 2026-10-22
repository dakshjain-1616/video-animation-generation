"""CLI. No server, no UI: every stage is a file you can read, diff and re-run.

Usage: python -m vga <command> ...
Commands: doctor, run, render, stills, inspect, list
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys

from .env import load_env
from .llm import resolve_llm_config
from .models import DEFAULT_ASPECT, DURATION_TOLERANCE, FORMATS
from .pipeline import (
    PACK_IDS,
    list_projects,
    load_plan,
    load_storyboard,
    project_dir,
    render_from_disk,
    run_project,
    stills_from_disk,
)
from .assets import AssetsError, load_assets
from . import music as soundtrack
from .render import renderer_available


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="vga",
        description='Prompt to a 20-60s code-generated animated explainer ("explainer" category).',
    )
    commands = parser.add_subparsers(dest="command")

    commands.add_parser("doctor", help="report tool, key and renderer status")

    run = commands.add_parser("run", help="prompt -> code -> video")
    run.add_argument("--idea", required=True, help="what the explainer should explain")
    run.add_argument("--target", type=float, default=30, help="video length in seconds (20-60)")
    run.add_argument("--category", default="explainer", choices=("explainer",))
    run.add_argument(
        "--pack",
        "--theme",
        dest="pack",
        choices=PACK_IDS,
        help="style theme/pack id (also VGA_PACK; default editorial-ink)",
    )
    run.add_argument(
        "--assets",
        help="path to an assets.json manifest, or the directory holding one",
    )
    run.add_argument(
        "--fetch-media",
        action="store_true",
        help="search and download relevant images (TAVILY_API_KEY) and stock clips (PEXELS_API_KEY) for the idea",
    )
    run.add_argument(
        "--aspect", default=DEFAULT_ASPECT, choices=tuple(FORMATS), help="frame shape: 9:16 for shorts (default) or 16:9"
    )
    run.add_argument(
        "--voice", action="store_true", help="add a voice-over (script + ElevenLabs speech); needs ELEVENLABS_API_KEY"
    )
    run.add_argument("--voice-id", help="ElevenLabs voice id (default: VGA_VOICE_ID or a stock narrator)")
    run.add_argument(
        "--music",
        nargs="?",
        const="auto",
        metavar="PATH|auto",
        help="optional background music: --music picks data/music/ or a generated cue, "
             "--music track.mp3 uses your file",
    )
    run.add_argument("--no-web-research", action="store_true", help="disable online UI/motion reference research (enabled by default with TAVILY_API_KEY)")
    run.add_argument("--no-review", action="store_true", help="skip the vision review of rendered frames")
    run.add_argument("--id", help="project id (defaults to a slug of idea + target)")

    render = commands.add_parser("render", help="re-render from storyboard.json, no LLM")
    render.add_argument("project")
    render.add_argument("--out")
    render.add_argument("--crf", type=int)

    stills = commands.add_parser("stills", help="render review stills")
    stills.add_argument("project")
    stills.add_argument("--frames", required=True)

    inspect = commands.add_parser("inspect", help="plan, storyboard, duration and QA for a project")
    inspect.add_argument("project")

    commands.add_parser("list", help="all projects")

    args = parser.parse_args(argv)
    handlers = {
        "doctor": doctor,
        "run": run_command,
        "render": render_command,
        "stills": stills_command,
        "inspect": inspect_command,
        "list": list_command,
    }
    if args.command not in handlers:
        parser.print_help()
        return 0

    load_env()
    try:
        return handlers[args.command](args)
    except Exception as error:  # one place to turn failures into a clean exit
        print(f"\n{error}", file=sys.stderr)
        return 1


def doctor(_args) -> int:
    print("Environment")
    print(f"  OK    python         {sys.version.split()[0]}")

    ffmpeg = shutil.which("ffmpeg")
    detail = _first_line(["ffmpeg", "-version"]) if ffmpeg else "not found: renders will fail"
    print(f"  {_flag(bool(ffmpeg))} ffmpeg         {detail}")

    ready, detail = renderer_available()
    print(f"  {_flag(ready)} renderer       {detail}")

    load_env()
    llm = resolve_llm_config()
    detail = llm.describe() if llm else "no key: put OPENROUTER_API_KEY in .env"
    print(f"  {_flag(bool(llm))} llm            {detail}")

    media = (
        "TAVILY_API_KEY present (--fetch-media: images"
        + (", PEXELS_API_KEY clips" if os.environ.get("PEXELS_API_KEY") else ", add PEXELS_API_KEY for clips")
        + ")"
        if os.environ.get("TAVILY_API_KEY")
        else "no TAVILY_API_KEY: --fetch-media unavailable (caller-provided assets still work)"
    )
    print(f"  media-fetch     {media}")
    print("  visual-research " + ("Tavily ready; enabled by default" if os.environ.get("TAVILY_API_KEY") else "unavailable: add TAVILY_API_KEY"))
    print(
        "  voice-over      "
        + ("ELEVENLABS_API_KEY present (run --voice)" if os.environ.get("ELEVENLABS_API_KEY")
           else "no ELEVENLABS_API_KEY: --voice unavailable (output stays silent)")
    )
    library = soundtrack.library_dir()
    tracks = sorted(p.name for p in library.iterdir() if p.suffix.lower() in soundtrack.MUSIC_EXTS) if library.is_dir() else []
    print(
        f"  music           --music: {'library ' + library.name + f' ({len(tracks)} track(s))' if tracks else 'generated cue'}"
        " or --music <file>"
    )

    projects = list_projects()
    print(f"\nProjects ({len(projects)}) in data/projects/")
    if not projects:
        print('  (none yet: run `python -m vga run --idea "..." --target 30`)')
    print(f"\nDuration gate: |actual - target| <= {DURATION_TOLERANCE:.1f}s, and 20s <= actual <= 60s.")
    return 0


def run_command(args) -> int:
    project_id = args.id or _slug(f"{args.idea}-{args.target:g}")
    error = _validate_project_id(project_id)
    if error:
        print(error, file=sys.stderr)
        return 1
    assets = None
    if args.assets:
        try:
            assets = load_assets(args.assets)
        except AssetsError as error:
            print(f"assets: {error}", file=sys.stderr)
            return 1
        print(f"assets: {len(assets)} loaded ({', '.join(asset.id for asset in assets)})")
    pack = args.pack or os.environ.get("VGA_PACK") or "editorial-ink"
    if pack not in PACK_IDS:
        print(f'Unknown theme "{pack}". Available: {", ".join(PACK_IDS)}.', file=sys.stderr)
        return 1
    try:
        result = run_project(
            project_id, args.idea, args.target, args.category, pack, assets, args.fetch_media,
            aspect=args.aspect, voice=args.voice, voice_id=args.voice_id, review=not args.no_review,
            music=args.music, web_research=not args.no_web_research,
        )
    except ValueError as error:
        print(f"{error}", file=sys.stderr)
        return 1
    duration = result["duration"]
    print("")
    print(f"Project  {result['dir']}")
    print(
        f"Duration Target {duration['target']:.1f}s · Actual {duration['actual']:.2f}s · "
        f"{duration['delta']:+.2f}s {'PASS' if duration['pass'] else 'FAIL'}"
    )
    if result["qa"]:
        print(f"QA       {'PASS' if result['qa']['pass'] else 'FAIL'}")
    print(f"Video    {result['video'] or '(not written: duration gate failed)'}")
    qa = result.get("qa") or {}
    return 0 if qa.get("pass", duration["pass"]) else 1


def render_command(args) -> int:
    result = render_from_disk(args.project, args.out, args.crf)
    print(
        f"Target {result['duration']['target']:.1f}s · Actual {result['duration']['actual']:.2f}s · "
        f"{result['duration']['delta']:+.2f}s {'PASS' if result['duration']['pass'] else 'FAIL'}"
    )
    return 0 if result["duration"]["pass"] else 1


def stills_command(args) -> int:
    frames = [int(value) for value in args.frames.split(",") if value.strip()]
    for output in stills_from_disk(args.project, frames):
        print(output)
    return 0


def inspect_command(args) -> int:
    directory = project_dir(args.project)
    run = _read(directory / "run.json") or {}
    plan, storyboard = run.get("plan") or load_plan(args.project), load_storyboard(args.project)
    duration = run.get("duration") or _read(directory / "duration.json")
    qa = run.get("qa") or _read(directory / "qa.json")
    codegen = run.get("codegen") or _read(directory / "codegen.json")
    preflight_report = run.get("preflight") or _read(directory / "preflight.json")

    print(f"Project {args.project}")
    research = run.get("research") or _read(directory / "research.json")
    if research:
        print(f"  Research {research.get('status', 'unknown')} ({len(research.get('sources', []))} references)")
    if qa:
        print(f"  QA       {'PASS' if qa.get('pass') else 'FAIL'}; review {qa.get('review', 'unknown')}")
    if plan:
        print(f"  Idea     {plan['idea']}")
        print(f"  Title    {plan['title']}")
        print(f"  Angle    {plan['angle']}")
    if codegen:
        print(f"  Code     scenes.tsx via {codegen['file']} (attempt {codegen['attempts']})")
    if storyboard:
        print(f"  Scenes   {len(storyboard['scenes'])}")
        for scene in storyboard["scenes"]:
            print(
                f"    {scene['id']}  {scene['seconds']:5.2f}s  {scene['frames']:4d}fr  "
                f"{scene['kind']:<5}  {scene['surface']:<5}  {scene['title'][:56]}"
            )
    if duration:
        print(
            f"  Duration target {duration['target']:g}s · actual {duration['actual']}s · "
            f"{duration['delta']:+.3f}s {'PASS' if duration['pass'] else 'FAIL'}"
        )
        print(f"  Frames   {duration['frames']} @ {duration['fps']}fps")
    if qa:
        print(f"  QA       {'PASS' if qa['pass'] else 'FAIL'}")
    if preflight_report:
        for warning in preflight_report.get("warnings", []):
            print(f"  Note     {warning}")
    audio = run.get("audio") or _read(directory / "audio" / "music.json")
    if audio:
        source = audio.get("file") or audio.get("source", "audio")
        print(f"  Audio    {source}" + (" (ducked under voice)" if audio.get("ducked") else ""))
    usage = run.get("usage") or _read(directory / "usage.json")
    if usage:
        estimate = usage.get("estimated_usd")
        print(
            f"  Usage    {usage['calls']} calls · {usage['input_tokens']} in / {usage['output_tokens']} out tok"
            + (f" · ≈${estimate:.4f}" if isinstance(estimate, (int, float)) else "")
        )

    files = sorted(path.name for path in directory.iterdir()) if directory.exists() else []
    print(f"  Files    {', '.join(files)}")
    return 0


def list_command(_args) -> int:
    projects = list_projects()
    if not projects:
        print('No projects yet. Try: python -m vga run --idea "how waves carry energy" --target 20')
        return 0
    for project in projects:
        print(
            f"  {project['id']:<32} {str(project.get('title') or '')[:36]:<36} "
            f"target {project['target']}s  actual {project['duration']}s  "
            f"{'PASS' if project['pass'] else 'FAIL'}"
        )
    return 0


def _read(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _slug(value: str) -> str:
    return re.sub(r"^-|-$", "", re.sub(r"[^a-z0-9]+", "-", value.lower()))[:48]


def _validate_project_id(project_id: str) -> str | None:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,47}", project_id):
        return f"Project id \"{project_id}\" must be lowercase letters, digits and dashes."
    project = project_dir(project_id)
    if project.exists() and not (project / "plan.json").exists() and not (project / "storyboard.json").exists():
        return f"Project {project_id} exists but is not a fully built project; choose another --id."
    return None


def _first_line(command: list[str]) -> str:
    try:
        output = subprocess.run(command, capture_output=True, text=True, check=True).stdout
        return output.splitlines()[0] if output else ""
    except (OSError, subprocess.SubprocessError):
        return "unavailable"


def _flag(ok: bool) -> str:
    return "OK  " if ok else "--  "


if __name__ == "__main__":
    raise SystemExit(main())
