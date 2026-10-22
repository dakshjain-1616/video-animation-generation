import { useCurrentFrame, useVideoConfig } from "remotion";
import { useTheme } from "../../lib/theme";
import { enterProgress } from "../../lib/motion";
import { useStage } from "../../lib/stage";

/**
 * FlowDiagram: a horizontal chain of labeled nodes with drawn-on connectors —
 * pipelines, decision flows, loops. Nodes pop in staggered, connectors ink
 * between them, and the highlighted node (by index) reads in the accent. When
 * the chain is wider than the stage it runs top to bottom instead.
 */
export const FlowDiagram = ({
  steps,
  x,
  y,
  nodeWidth = 300,
  nodeHeight = 96,
  gap = 64,
  highlight,
  delay = 0,
  labels,
}: {
  steps: string[];
  x: number;
  y: number;
  nodeWidth?: number;
  nodeHeight?: number;
  gap?: number;
  /** Node index to render in the accent tone (the point of the flow). */
  highlight?: number;
  delay?: number;
  /** One-line sub-labels under each node (same length as steps). */
  labels?: string[];
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const { pack, colors } = useTheme();
  const stage = useStage();
  const last = steps.length - 1;
  const rowWidth = steps.length * nodeWidth + last * gap;

  if (rowWidth > stage.right - x) {
    // Too wide for the stage (portrait): same chain, top to bottom.
    const width = Math.min(nodeWidth, stage.right - x);
    const drop = Math.max(40, gap);
    return (
      <div style={{ position: "absolute", left: x, top: y, width }}>
        {steps.map((step, index) => {
          const enter = enterProgress(frame, fps, delay + index * 0.22, 0.5);
          const connector = enterProgress(frame, fps, delay + index * 0.22 + 0.18, 0.35);
          const accent = highlight === index;
          const tone = accent ? colors.accent : colors.fg;
          return (
            <div key={step}>
              <div
                style={{
                  boxSizing: "border-box",
                  width,
                  minHeight: nodeHeight,
                  border: `${pack.stroke.hair + 1}px solid ${tone}`,
                  background: accent ? `${colors.accent}14` : "transparent",
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "center",
                  justifyContent: "center",
                  gap: 6,
                  padding: "10px 16px",
                  opacity: enter,
                  transform: `translateY(${(1 - enter) * 10}px)`,
                }}
              >
                <span
                  style={{
                    fontFamily: pack.fonts.mono,
                    fontSize: pack.type.label.md,
                    letterSpacing: "0.1em",
                    textTransform: "uppercase",
                    color: tone,
                    textAlign: "center",
                    lineHeight: 1.15,
                  }}
                >
                  {step}
                </span>
                {labels?.[index] ? (
                  <span
                    style={{
                      fontFamily: pack.fonts.mono,
                      fontSize: pack.type.label.sm,
                      letterSpacing: "0.12em",
                      color: colors.sub,
                      textAlign: "center",
                    }}
                  >
                    {labels[index]}
                  </span>
                ) : null}
              </div>
              {index < last ? (
                <svg width={width} height={drop} viewBox={`0 0 ${width} ${drop}`} fill="none" style={{ display: "block" }}>
                  <path
                    d={`M${width / 2} 0 V${drop - 8}`}
                    stroke={colors.sub}
                    strokeWidth={pack.stroke.hair + 1}
                    pathLength={1}
                    style={{ strokeDasharray: 1, strokeDashoffset: 1 - connector }}
                  />
                  <path
                    d={`M${width / 2 - 6} ${drop - 12} L${width / 2} ${drop - 4} L${width / 2 + 6} ${drop - 12}`}
                    stroke={colors.sub}
                    strokeWidth={pack.stroke.hair + 1}
                    strokeLinecap="round"
                    opacity={connector}
                  />
                </svg>
              ) : null}
            </div>
          );
        })}
      </div>
    );
  }

  return (
    <div style={{ position: "absolute", left: x, top: y }}>
      <div style={{ display: "flex", position: "relative" }}>
        {steps.map((step, index) => {
          const enter = enterProgress(frame, fps, delay + index * 0.22, 0.5);
          const connector = enterProgress(frame, fps, delay + index * 0.22 + 0.18, 0.35);
          const arrow = enterProgress(frame, fps, delay + index * 0.22 + 0.3, 0.3);
          const accent = highlight === index;
          return (
            <div
              key={step}
              style={{ width: index < last ? nodeWidth + gap : nodeWidth, flexShrink: 0, position: "relative" }}
            >
              <div
                style={{
                  width: nodeWidth,
                  height: nodeHeight,
                  border: `${pack.stroke.hair + 1}px solid ${accent ? colors.accent : colors.fg}`,
                  background: accent ? `${colors.accent}14` : "transparent",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  padding: "8px 14px",
                  opacity: enter,
                  transform: `translateY(${(1 - enter) * 10}px)`,
                }}
              >
                <span
                  style={{
                    fontFamily: pack.fonts.mono,
                    fontSize: pack.type.label.md,
                    letterSpacing: "0.1em",
                    textTransform: "uppercase",
                    color: accent ? colors.accent : colors.fg,
                    textAlign: "center",
                    lineHeight: 1.15,
                  }}
                >
                  {step}
                </span>
              </div>
              {index < last ? (
                <svg
                  width={gap}
                  height={14}
                  viewBox={`0 0 ${gap} 14`}
                  fill="none"
                  style={{
                    position: "absolute",
                    // Vertically centered on the node box.
                    top: (nodeHeight - 14) / 2,
                    left: nodeWidth,
                    flexShrink: 0,
                  }}
                >
                  <path
                    d={`M0 7 H${gap - 8}`}
                    stroke={colors.sub}
                    strokeWidth={pack.stroke.hair + 1}
                    pathLength={1}
                    style={{ strokeDasharray: 1, strokeDashoffset: 1 - connector }}
                  />
                  <path
                    d={`M${gap - 12} 2 L${gap - 4} 7 L${gap - 12} 12`}
                    stroke={colors.sub}
                    strokeWidth={pack.stroke.hair + 1}
                    fill="none"
                    strokeLinecap="round"
                    opacity={arrow}
                  />
                </svg>
              ) : null}
            </div>
          );
        })}
      </div>
      {labels ? (
        <div style={{ display: "flex" }}>
          {steps.map((step, index) => {
            const enter = enterProgress(frame, fps, delay + index * 0.22 + 0.3, 0.4);
            return (
              <div
                key={step}
                style={{
                  width: index < last ? nodeWidth + gap : nodeWidth,
                  flexShrink: 0,
                  opacity: enter,
                  fontFamily: pack.fonts.mono,
                  fontSize: pack.type.label.sm,
                  letterSpacing: "0.12em",
                  color: colors.sub,
                  textAlign: nodeWidth > 200 ? "center" : "left",
                }}
              >
                {labels[index] ?? ""}
              </div>
            );
          })}
        </div>
      ) : null}
    </div>
  );
};
