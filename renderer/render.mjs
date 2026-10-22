#!/usr/bin/env node
/**
 * Render service.
 *
 * This is the only Node-side entry point the Python agent uses. Contract:
 * in  - a storyboard.json (schema-checked) whose `entry` points at a generated
 *       Remotion entry for the project
 * out - an MP4, plus a duration report on stdout as one JSON object
 *
 * Everything else in the system is Python. Run with: npx tsx renderer/render.mjs
 */
import fs from "node:fs";
import { renderStills, renderStoryboard } from "../src/render.ts";
import { storyboardSchema } from "../src/schema/storyboard.ts";

const args = new Map();
for (let i = 2; i < process.argv.length; i += 2) {
  const key = process.argv[i];
  if (!key.startsWith("--")) continue;
  args.set(key.slice(2), process.argv[i + 1]);
}

function required(name) {
  const value = args.get(name);
  if (!value) {
    console.error(`render: missing --${name}`);
    process.exit(2);
  }
  return value;
}

function log(line) {
  console.error(line);
}

async function main() {
  const storyboard = storyboardSchema.parse(
    JSON.parse(fs.readFileSync(required("storyboard"), "utf8")),
  );

  if (args.has("frames")) {
    const frames = String(args.get("frames"))
      .split(",")
      .map((value) => Number(value.trim()))
      .filter(Number.isFinite);
    const outputs = await renderStills({
      storyboard,
      frames,
      outDir: args.get("stills-dir") ?? "qa/frames",
    });
    process.stdout.write(`${JSON.stringify({ ok: true, stills: outputs })}\n`);
    return;
  }

  const out = required("out");
  log(`render: ${storyboard.scenes.length} scenes -> ${out}`);
  const result = await renderStoryboard({
    storyboard,
    outFile: out,
    crf: args.has("crf") ? Number(args.get("crf")) : undefined,
  });

  process.stdout.write(
    `${JSON.stringify({
      ok: true,
      file: result.file,
      target: result.target,
      actual: result.actual,
      delta: result.delta,
      pass: result.pass,
      frames: result.frames,
      renderSeconds: result.renderSeconds,
      containerDuration: result.info.containerDuration,
      videoDuration: result.info.video?.duration ?? null,
      audioDuration: result.info.audio?.duration ?? null,
      width: result.info.video?.width ?? null,
      height: result.info.video?.height ?? null,
      fps: result.info.video?.fps ?? null,
      sizeBytes: result.info.sizeBytes,
    })}\n`,
  );

  if (!result.pass) process.exit(1);
}

main().catch((error) => {
  console.error(`render failed: ${error instanceof Error ? error.message : String(error)}`);
  process.exit(1);
});
