import { useCurrentFrame, useVideoConfig } from "remotion";
import { useTheme } from "../../lib/theme";
import { enterProgress } from "../../lib/motion";
/**
 * IconGlyph: a drawn stroke pictogram — the drawn-visual vocabulary for scenes
 * that are not media scenes. Pure SVG strokes colored from tokens, ink-drawn
 * with a path-length reveal so icons feel inked, not pasted.
 *
 * Icons are simple geometric constructions on a 24x24 grid: chip, bot,
 * shield (check), balance, gauge, network, doc, bank, bell, mic, headphones,
 * clock, chart, globe, lock, plane, person, target, search, gear, alert.
 * Scale with `size`, tint with `tone`.
 */
export const ICON_NAMES = [
  "chip",
  "bot",
  "shield",
  "balance",
  "gauge",
  "network",
  "doc",
  "bank",
  "bell",
  "mic",
  "headphones",
  "clock",
  "chart",
  "globe",
  "lock",
  "plane",
  "person",
  "target",
  "search",
  "gear",
  "alert",
] as const;

export type IconName = (typeof ICON_NAMES)[number];

const PATHS: Record<IconName, string[]> = {
  chip: [
    "M7 7 H17 V17 H7 Z",
    "M10 2 V7", "M14 2 V7", "M10 17 V22", "M14 17 V22",
    "M2 10 H7", "M2 14 H7", "M17 10 H22", "M17 14 H22",
    "M10.5 10.5 H13.5 V13.5 H10.5 Z",
  ],
  bot: [
    "M5 9 H19 V18 H5 Z",
    "M12 3 V9",
    "M9.5 6 H14.5",
    "M9.5 12.5 H10.5", "M13.5 12.5 H14.5",
    "M3 12 V15", "M21 12 V15",
    "M9 18 V20", "M15 18 V20",
  ],
  shield: [
    "M12 2 L20 5.5 V11 C20 16.5 16.5 20 12 22 C7.5 20 4 16.5 4 11 V5.5 Z",
    "M8.5 11.5 L11 14 L15.5 9.5",
  ],
  balance: [
    "M12 4 V20",
    "M5 7 H19",
    "M3 7 L6.5 13.5 H1.5 Z",
    "M21 7 L22.5 13.5 H17.5 Z",
    "M4.5 13.5 H8.5",
    "M6.5 20 H17.5",
  ],
  gauge: [
    "M4 16 A9 9 0 0 1 20 16",
    "M12 16 L18 8",
    "M12 20.5 L12 16",
  ],
  network: [
    "M7 7 C7 5.3 5.7 4 4 4 C2.3 4 1 5.3 1 7 C1 8.7 2.3 10 4 10 C5.7 10 7 8.7 7 7 Z",
    "M23 6 A3 3 0 1 1 17 6 A3 3 0 1 1 23 6 Z",
    "M16 18 A3 3 0 1 1 10 18 A3 3 0 1 1 16 18 Z",
    "M7 8.5 L14 16.5",
    "M20 9 L13.5 15.8",
  ],
  doc: [
    "M6 2 H14 L19 7 V22 H6 Z",
    "M14 2 V7 H19",
    "M9 11 H16", "M9 15 H16", "M9 19 H13",
  ],
  bank: [
    "M3 9 L12 3 L21 9",
    "M5 9 V18", "M9.5 9 V18", "M14.5 9 V18", "M19 9 V18",
    "M3 18 H21 V20.5 H3 Z",
  ],
  bell: [
    "M6 16 V10 C6 6.7 8.7 4 12 4 C15.3 4 18 6.7 18 10 V16",
    "M4 16 H20",
    "M12 16 V19.5 C12 20.6 11.1 21.5 10 21.5 C8.9 21.5 8 20.6 8 19.5",
  ],
  mic: [
    "M12 3 C10.3 3 9 4.3 9 6 V12 C9 13.7 10.3 15 12 15 C13.7 15 15 13.7 15 12 V6 C15 4.3 13.7 3 12 3 Z",
    "M6 11 V12 C6 15.3 8.7 18 12 18 C15.3 18 18 15.3 18 12 V11",
    "M12 18 V21",
    "M9 21 H15",
  ],
  headphones: [
    "M4 14 V12 C4 7.6 7.6 4 12 4 C16.4 4 20 7.6 20 12 V14",
    "M4 14 H7 V20 H5.5 C4.7 20 4 19.3 4 18.5 Z",
    "M20 14 H17 V20 H18.5 C19.3 20 20 19.3 20 18.5 Z",
  ],
  clock: [
    "M12 3 A9 9 0 1 1 11.9 3 Z",
    "M12 7 V12 L15.5 14",
  ],
  chart: [
    "M4 4 V20 H21",
    "M7 16 L11 10 L14 13 L19 6",
  ],
  globe: [
    "M12 2 A10 10 0 1 1 11.9 2 Z",
    "M2 12 H22",
    "M12 2 C15 5 16 8.5 16 12 C16 15.5 15 19 12 22",
    "M12 2 C9 5 8 8.5 8 12 C8 15.5 9 19 12 22",
  ],
  lock: [
    "M6 10 H18 V21 H6 Z",
    "M9 10 V7 C9 5.3 10.3 4 12 4 C13.7 4 15 5.3 15 7 V10",
    "M12 14 V17",
  ],
  plane: [
    "M2 13 L22 4 L15 22 L11.5 14.5 Z",
    "M22 4 L11.5 14.5",
  ],
  person: [
    "M12 4 A3.5 3.5 0 1 1 11.9 4 Z",
    "M5 21 C5 16.6 8.1 14 12 14 C15.9 14 19 16.6 19 21",
  ],
  target: [
    "M12 3 A9 9 0 1 1 11.9 3 Z",
    "M12 8 A4 4 0 1 1 11.9 8 Z",
    "M12 11 V12",
  ],
  search: [
    "M11 4 A7 7 0 1 1 10.9 4 Z",
    "M16.5 16.5 L21 21",
    "M11 8 V14", "M8 11 H14",
  ],
  gear: [
    "M12 8 A4.5 4.5 0 1 1 11.9 8 Z",
    "M12 2 V4.5", "M12 19.5 V22", "M2 12 H4.5", "M19.5 12 H22",
    "M4.9 4.9 L6.7 6.7", "M17.3 17.3 L19.1 19.1",
    "M4.9 19.1 L6.7 17.3", "M17.3 6.7 L19.1 4.9",
  ],
  alert: [
    "M12 3 L22 20 H2 Z",
    "M12 9.5 V14",
    "M12 16.5 V17",
  ],
};

export const IconGlyph = ({
  name,
  x,
  y,
  size = 120,
  tone = "ink",
  delay = 0,
  duration = 0.7,
  label,
}: {
  name: IconName;
  x: number;
  y: number;
  size?: number;
  /** "ink" | "accent" | "muted" — token, never a raw color. */
  tone?: "ink" | "accent" | "muted";
  delay?: number;
  duration?: number;
  label?: string;
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const { pack, colors } = useTheme();
  const progress = enterProgress(frame, fps, delay, duration);
  const stroke = tone === "accent" ? colors.accent : tone === "muted" ? colors.sub : colors.fg;

  return (
    <div
      style={{
        position: "absolute",
        left: x,
        top: y,
        opacity: Math.min(1, progress * 1.4),
      }}
    >
      <svg
        width={size}
        height={size}
        viewBox="0 0 24 24"
        fill="none"
        stroke={stroke}
        strokeWidth={1.4}
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        {PATHS[name].map((d, index) => (
          <path
            key={index}
            d={d}
            pathLength={1}
            // Later sub-paths ink in after earlier ones: a drafting feel.
            style={{
              strokeDasharray: 1,
              strokeDashoffset: Math.max(0, 1 - progress * 1.6 + index * 0.08),
            }}
          />
        ))}
      </svg>
      {label ? (
        <div
          style={{
            marginTop: size * 0.12,
            fontFamily: pack.fonts.mono,
            fontSize: pack.type.label.sm,
            letterSpacing: "0.16em",
            textTransform: "uppercase",
            textAlign: "center",
            whiteSpace: "nowrap",
            color: colors.sub,
            opacity: progress,
          }}
        >
          {label}
        </div>
      ) : null}
    </div>
  );
};
