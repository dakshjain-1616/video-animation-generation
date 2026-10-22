import { useMemo } from "react";
import { useCurrentFrame, useVideoConfig } from "remotion";
import { resolveColor, useTheme } from "../../lib/theme";
import { enterProgress } from "../../lib/motion";
import { makeRng, range } from "../../lib/rng";

export type Curve = "sine" | "decay" | "growth" | "steps" | "noise" | "spike";

const SAMPLES = 160;

/** y in 0..1 (1 = top of the plot) for x in 0..1. */
const curveValue = (curve: Curve, t: number, noise: number[]): number => {
  switch (curve) {
    case "sine":
      return 0.5 + 0.38 * Math.sin(t * Math.PI * 6);
    case "decay":
      return 0.1 + 0.8 * Math.exp(-3.4 * t) * (0.7 + 0.3 * Math.cos(t * Math.PI * 10));
    case "growth":
      return 0.08 + 0.84 * Math.pow(t, 2.2);
    case "steps":
      return 0.12 + 0.19 * Math.min(4, Math.floor(t * 5));
    case "spike":
      return 0.18 + 0.72 * Math.exp(-Math.pow((t - 0.55) / 0.07, 2));
    case "noise":
      return 0.5 + 0.38 * noise[Math.min(noise.length - 1, Math.floor(t * (noise.length - 1)))];
  }
};

/**
 * SignalPlot: a labeled chart frame (axes + one drawn curve + a leading dot) —
 * for "how X changes over Y" without inventing numbers. The curve shape is a
 * qualitative archetype, not data.
 */
export const SignalPlot = ({
  x,
  y,
  width,
  height,
  curve = "sine",
  xLabel,
  yLabel,
  color,
  delay = 0,
  duration = 1.2,
  seed = 7,
}: {
  x: number;
  y: number;
  width: number;
  height: number;
  curve?: Curve;
  xLabel?: string;
  yLabel?: string;
  color?: string;
  delay?: number;
  duration?: number;
  seed?: number;
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const { pack, colors } = useTheme();
  const axes = enterProgress(frame, fps, delay, 0.5);
  const draw = enterProgress(frame, fps, delay + 0.35, duration);
  const stroke = resolveColor(color, colors, colors.accent);
  const pad = 36;
  const plotW = width - pad;
  const plotH = height - pad;

  const points = useMemo(() => {
    const rng = makeRng(seed);
    const noise: number[] = [];
    let level = 0;
    for (let i = 0; i < 24; i += 1) {
      level = Math.max(-1, Math.min(1, level * 0.55 + range(rng, -1, 1) * 0.7));
      noise.push(level);
    }
    return Array.from({ length: SAMPLES }, (_, i) => {
      const t = i / (SAMPLES - 1);
      return { x: pad + t * plotW, y: plotH - curveValue(curve, t, noise) * plotH };
    });
  }, [curve, seed, plotW, plotH]);

  const d = points.map((p, i) => `${i ? "L" : "M"}${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(" ");
  const head = points[Math.min(SAMPLES - 1, Math.round(draw * (SAMPLES - 1)))];
  const labelStyle = {
    position: "absolute" as const,
    fontFamily: pack.fonts.mono,
    fontSize: pack.type.label.sm,
    letterSpacing: "0.18em",
    textTransform: "uppercase" as const,
    color: colors.sub,
    whiteSpace: "nowrap" as const,
    opacity: axes,
  };

  return (
    <div style={{ position: "absolute", left: x, top: y, width, height: height + 40 }}>
      <svg width={width} height={height} fill="none" style={{ overflow: "visible" }}>
        <path
          d={`M${pad} 0 V${plotH} H${width}`}
          stroke={colors.fg}
          strokeWidth={pack.stroke.hair + 1}
          strokeLinecap="round"
          pathLength={1}
          style={{ strokeDasharray: 1, strokeDashoffset: 1 - axes }}
        />
        <path
          d={d}
          stroke={stroke}
          strokeWidth={pack.stroke.regular}
          strokeLinecap="round"
          strokeLinejoin="round"
          pathLength={1}
          style={{ strokeDasharray: 1, strokeDashoffset: 1 - draw }}
        />
        <circle cx={head.x} cy={head.y} r={11} fill={stroke} opacity={draw > 0.02 ? 1 : 0} />
      </svg>
      {xLabel ? <div style={{ ...labelStyle, right: 0, top: height + 10 }}>{xLabel}</div> : null}
      {yLabel ? <div style={{ ...labelStyle, left: pad + 10, top: -4 }}>{yLabel}</div> : null}
    </div>
  );
};
