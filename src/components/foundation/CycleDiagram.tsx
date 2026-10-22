import { useCurrentFrame, useVideoConfig } from "remotion";
import { useTheme } from "../../lib/theme";
import { enterProgress } from "../../lib/motion";
import { estimateTextWidth } from "../../lib/layout";

const rad = (deg: number) => (deg * Math.PI) / 180;

/**
 * CycleDiagram: 3-5 labeled nodes on a ring with drawn arrows between them and
 * a dot that keeps circling — feedback loops, repeating processes. `cx, cy` is
 * the ring's center; labels sit centered on their node.
 */
export const CycleDiagram = ({
  steps,
  cx,
  cy,
  radius = 230,
  highlight,
  centerLabel,
  delay = 0,
}: {
  steps: string[];
  cx: number;
  cy: number;
  radius?: number;
  highlight?: number;
  centerLabel?: string;
  delay?: number;
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const { pack, colors } = useTheme();
  const count = steps.length;
  const size = pack.type.label.md;
  const angleOf = (i: number) => -90 + (360 / count) * i;
  const pointAt = (deg: number) => ({ x: cx + radius * Math.cos(rad(deg)), y: cy + radius * Math.sin(rad(deg)) });

  // Arrows leave room around each pill: the pill's half-width as an angle.
  const pillWidth = (label: string) => estimateTextWidth(label, size, 0.1, "mono") + 40;
  const clearance = (label: string) => (pillWidth(label) / 2 / radius) * (180 / Math.PI) + 4;

  const orbit = enterProgress(frame, fps, delay + count * 0.25, 0.4);
  const spin = -90 + ((frame / fps) * 360) / 4; // one lap every 4 seconds

  return (
    <>
      <svg
        width={cx * 2}
        height={cy * 2}
        style={{ position: "absolute", left: 0, top: 0, overflow: "visible" }}
        fill="none"
      >
        {steps.map((label, i) => {
          const next = steps[(i + 1) % count];
          const from = angleOf(i) + Math.min(clearance(label), 360 / count / 2 - 6);
          const to = angleOf(i + 1) - Math.min(clearance(next), 360 / count / 2 - 6);
          const a = pointAt(from);
          const b = pointAt(to);
          const progress = enterProgress(frame, fps, delay + i * 0.25 + 0.2, 0.45);
          const tangent = rad(to + 90);
          const head = (turn: number) => ({
            x: b.x - 16 * Math.cos(tangent + turn),
            y: b.y - 16 * Math.sin(tangent + turn),
          });
          const [h1, h2] = [head(0.5), head(-0.5)];
          return (
            <g key={label}>
              <path
                d={`M${a.x} ${a.y} A${radius} ${radius} 0 0 1 ${b.x} ${b.y}`}
                stroke={colors.sub}
                strokeWidth={pack.stroke.hair + 1}
                pathLength={1}
                style={{ strokeDasharray: 1, strokeDashoffset: 1 - progress }}
              />
              <path
                d={`M${h1.x} ${h1.y} L${b.x} ${b.y} L${h2.x} ${h2.y}`}
                stroke={colors.sub}
                strokeWidth={pack.stroke.hair + 1}
                strokeLinecap="round"
                strokeLinejoin="round"
                opacity={progress > 0.95 ? 1 : 0}
              />
            </g>
          );
        })}
        <circle
          cx={pointAt(spin).x}
          cy={pointAt(spin).y}
          r={9}
          fill={colors.accent}
          opacity={orbit}
        />
      </svg>
      {steps.map((label, i) => {
        const p = pointAt(angleOf(i));
        const enter = enterProgress(frame, fps, delay + i * 0.25, 0.5);
        const accent = highlight === i;
        const tone = accent ? colors.accent : colors.fg;
        return (
          <div
            key={label}
            style={{
              position: "absolute",
              left: p.x,
              top: p.y,
              transform: `translate(-50%, -50%) scale(${0.9 + 0.1 * enter})`,
              width: pillWidth(label),
              boxSizing: "border-box",
              padding: "14px 0",
              textAlign: "center",
              background: colors.bg,
              border: `${pack.stroke.hair + 1}px solid ${tone}`,
              opacity: enter,
              fontFamily: pack.fonts.mono,
              fontSize: size,
              letterSpacing: "0.1em",
              textTransform: "uppercase",
              color: tone,
              whiteSpace: "nowrap",
            }}
          >
            {label}
          </div>
        );
      })}
      {centerLabel ? (
        <div
          style={{
            position: "absolute",
            left: cx,
            top: cy,
            transform: "translate(-50%, -50%)",
            fontFamily: pack.fonts.display,
            fontSize: pack.type.label.lg,
            textTransform: "uppercase",
            color: colors.fg,
            opacity: enterProgress(frame, fps, delay + count * 0.25, 0.5),
            textAlign: "center",
            maxWidth: radius * 0.9,
          }}
        >
          {centerLabel}
        </div>
      ) : null}
    </>
  );
};
