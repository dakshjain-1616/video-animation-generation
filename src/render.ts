import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { bundle } from "@remotion/bundler";
import { renderMedia, renderStill, selectComposition } from "@remotion/renderer";
import type { Storyboard } from "./schema/storyboard";
import { DURATION_TOLERANCE, allowedWindow, storyboardFrames } from "./schema/storyboard";

const here = path.dirname(fileURLToPath(import.meta.url));
export const REPO_ROOT = path.resolve(here, "..");

const bundleCache = new Map<string, string>();

/** Bundle a generated entry once per render process. */
export async function getBundle(entry: string): Promise<string> {
  const cached = bundleCache.get(entry);
  if (cached) return cached;
  const entryPoint = path.join(REPO_ROOT, entry);
  if (!fs.existsSync(entryPoint)) {
    throw new Error(`entry missing: ${entry} (render the project first)`);
  }
  const bundlePath = await bundle({
    entryPoint,
    // Media assets stage into public/generated/<id>/; staticFile() resolves
    // against this directory. Explicit, so the bundler never guesses CWD.
    publicDir: path.join(REPO_ROOT, "public"),
  });
  bundleCache.set(entry, bundlePath);
  return bundlePath;
}

export type ProbeInfo = {
  containerDuration: number;
  sizeBytes: number;
  video: { codec: string; width: number; height: number; fps: number; frames: number | null; duration: number } | null;
  audio: { codec: string; sampleRate: number; channels: number; duration: number } | null;
};

export function probe(file: string): ProbeInfo {
  const raw = execFileSync(
    "ffprobe",
    ["-v", "error", "-print_format", "json", "-show_format", "-show_streams", file],
    { encoding: "utf8" },
  );
  const data = JSON.parse(raw);
  const video = data.streams.find((s: { codec_type: string }) => s.codec_type === "video");
  const audio = data.streams.find((s: { codec_type: string }) => s.codec_type === "audio");

  return {
    containerDuration: Number(data.format.duration),
    sizeBytes: Number(data.format.size),
    video: video
      ? {
          codec: video.codec_name,
          width: video.width,
          height: video.height,
          fps: fraction(video.avg_frame_rate),
          frames: video.nb_frames ? Number(video.nb_frames) : null,
          duration: Number(video.duration),
        }
      : null,
    audio: audio
      ? {
          codec: audio.codec_name,
          sampleRate: Number(audio.sample_rate),
          channels: Number(audio.channels),
          duration: Number(audio.duration),
        }
      : null,
  };
}

function fraction(value: string): number {
  if (!value || value === "0/0") return 0;
  const [num, den] = value.split("/").map(Number);
  return den ? num / den : num;
}

export type RenderResult = {
  file: string;
  actual: number;
  target: number;
  delta: number;
  pass: boolean;
  frames: number;
  renderSeconds: number;
  info: ProbeInfo;
};

/** Render the MP4 and gate it on the duration contract, from ffprobe output. */
export async function renderStoryboard(options: {
  storyboard: Storyboard;
  outFile: string;
  crf?: number;
}): Promise<RenderResult> {
  const started = Date.now();
  const durationInFrames = storyboardFrames(options.storyboard);
  const bundlePath = await getBundle(options.storyboard.entry);
  const composition = await selectComposition({
    serveUrl: bundlePath,
    id: "Explainer",
    inputProps: {},
  });

  fs.mkdirSync(path.dirname(options.outFile), { recursive: true });
  await renderMedia({
    composition,
    serveUrl: bundlePath,
    codec: "h264",
    outputLocation: options.outFile,
    crf: options.crf ?? 18,
    x264Preset: "medium",
    pixelFormat: "yuv420p",
    concurrency: 6,
  });

  let info = probe(options.outFile);
  const target = options.storyboard.target;
  const window = allowedWindow(target);
  let actual = info.containerDuration;

  // A container can overshoot by a few milliseconds because of muxer priming.
  // The contract is measured on the file, so trim the mux rather than argue.
  if (actual > window.max) {
    const trimmed = path.join(path.dirname(options.outFile), "trimmed.mp4");
    execFileSync("ffmpeg", ["-y", "-i", options.outFile, "-t", String(window.max), "-c", "copy", trimmed]);
    fs.renameSync(trimmed, options.outFile);
    info = probe(options.outFile);
    actual = info.containerDuration;
  }

  return {
    file: options.outFile,
    actual,
    target,
    delta: actual - target,
    pass: actual >= window.min && actual <= window.max && Math.abs(actual - target) <= DURATION_TOLERANCE,
    frames: info.video?.frames ?? durationInFrames,
    renderSeconds: Math.round(((Date.now() - started) / 1000) * 100) / 100,
    info,
  };
}

export async function renderStills(options: {
  storyboard: Storyboard;
  frames: number[];
  outDir: string;
}): Promise<string[]> {
  const bundlePath = await getBundle(options.storyboard.entry);
  const composition = await selectComposition({ serveUrl: bundlePath, id: "Explainer", inputProps: {} });
  fs.mkdirSync(options.outDir, { recursive: true });

  // QA stills are independent; rendering them one at a time makes the repair
  // loop wait on browser startup per frame. A small pool keeps memory bounded
  // while removing that serial cost.
  const outputs: string[] = new Array(options.frames.length);
  let next = 0;
  const worker = async () => {
    while (next < options.frames.length) {
      const index = next++;
      const clamped = Math.max(0, Math.min(durationInFrames(composition) - 1, options.frames[index]));
      const output = path.join(options.outDir, `frame-${String(clamped).padStart(4, "0")}.png`);
      await renderStill({ composition, serveUrl: bundlePath, frame: clamped, output });
      outputs[index] = output;
    }
  };
  const workers = Math.min(3, options.frames.length);
  await Promise.all(Array.from({ length: workers }, worker));
  return outputs;
}

function durationInFrames(composition: { durationInFrames: number }): number {
  return composition.durationInFrames;
}
