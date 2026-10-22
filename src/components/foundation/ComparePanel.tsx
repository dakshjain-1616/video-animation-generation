import { useCurrentFrame, useVideoConfig } from "remotion";
import { useTheme } from "../../lib/theme";
import { enterProgress } from "../../lib/motion";
import { useStage } from "../../lib/stage";

/**
 * ComparePanel: two face-off panels — "the old way" (muted, struck rows) vs
 * "the new way" (accent edge). Rows ink in staggered. On a narrow stage the
 * panels stack instead of sitting side by side.
 */
export const ComparePanel = ({
  before,
  after,
  x,
  y,
  width = 720,
  rowHeight = 64,
  gap = 40,
  delay = 0,
}: {
  before: { label: string; rows: string[] };
  after: { label: string; rows: string[] };
  x: number;
  y: number;
  width?: number;
  rowHeight?: number;
  gap?: number;
  delay?: number;
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const { pack, colors } = useTheme();
  const stage = useStage();
  // Side by side when both panels fit the stage; stacked (full-width) otherwise.
  const room = stage.right - x;
  const stacked = width * 2 + gap > room;
  const panelWidth = stacked ? Math.min(width * 2 + gap, room) : width;

  const Panel = ({
    panel,
    side,
    baseDelay,
  }: {
    panel: { label: string; rows: string[] };
    side: "before" | "after";
    baseDelay: number;
  }) => {
    const accent = side === "after";
    const headEnter = enterProgress(frame, fps, baseDelay, 0.45);
    return (
      <div
        style={{
          width: panelWidth,
          boxSizing: "border-box",
          padding: "20px 24px 24px",
          border: `${pack.stroke.hair + 1}px solid ${accent ? colors.accent : colors.sub}`,
          borderLeft: `${pack.stroke.regular}px solid ${accent ? colors.accent : colors.sub}`,
          background: accent ? `${colors.accent}0A` : "transparent",
          opacity: headEnter,
          transform: `translateY(${(1 - headEnter) * 10}px)`,
        }}
      >
        <div
          style={{
            fontFamily: pack.fonts.mono,
            fontSize: pack.type.label.md,
            letterSpacing: "0.2em",
            textTransform: "uppercase",
            color: accent ? colors.accent : colors.sub,
            marginBottom: 14,
          }}
        >
          {panel.label}
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {panel.rows.map((row, index) => {
            const enter = enterProgress(frame, fps, baseDelay + 0.12 + index * 0.12, 0.4);
            return (
              <div
                key={row}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 14,
                  minHeight: rowHeight,
                  opacity: enter,
                  transform: `translateX(${(1 - enter) * -14}px)`,
                }}
              >
                <span
                  style={{
                    width: 26,
                    height: 26,
                    flexShrink: 0,
                    borderRadius: "50%",
                    border: `${pack.stroke.hair + 1}px solid ${accent ? colors.accent : colors.sub}`,
                    color: accent ? colors.accent : colors.sub,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontFamily: pack.fonts.mono,
                    fontSize: pack.type.label.sm,
                  }}
                >
                  {accent ? "+" : "x"}
                </span>
                <span
                  style={{
                    fontFamily: pack.fonts.text,
                    fontWeight: 600,
                    fontSize: pack.type.body.md,
                    color: colors.fg,
                    textDecoration: accent ? "none" : "line-through",
                    textDecorationColor: colors.sub,
                  }}
                >
                  {row}
                </span>
              </div>
            );
          })}
        </div>
      </div>
    );
  };

  return (
    <div style={{ position: "absolute", left: x, top: y, display: "flex", flexDirection: stacked ? "column" : "row", gap }}>
      <Panel panel={before} side="before" baseDelay={delay} />
      <Panel panel={after} side="after" baseDelay={delay + 0.25} />
    </div>
  );
};
