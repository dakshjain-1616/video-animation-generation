import { useCurrentFrame, useVideoConfig } from "remotion";
import { useTheme } from "../../lib/theme";
import { enterProgress } from "../../lib/motion";

/**
 * LayerStack: labeled slabs stacked bottom to top — architectures, "layers of
 * a system", things built on other things. The first step is the base and
 * enters first; `highlight` (index from the bottom) reads in the accent.
 */
export const LayerStack = ({
  layers,
  x,
  y,
  width,
  layerHeight = 96,
  gap = 14,
  highlight,
  delay = 0,
  labels,
}: {
  /** Bottom layer first. */
  layers: string[];
  x: number;
  y: number;
  width: number;
  layerHeight?: number;
  gap?: number;
  highlight?: number;
  delay?: number;
  /** One short note per layer, shown on the right of the slab. */
  labels?: string[];
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const { pack, colors } = useTheme();
  const total = layers.length * layerHeight + (layers.length - 1) * gap;

  return (
    <div style={{ position: "absolute", left: x, top: y, width, height: total }}>
      {layers.map((layer, index) => {
        const enter = enterProgress(frame, fps, delay + index * 0.2, 0.5);
        const accent = highlight === index;
        const tone = accent ? colors.accent : colors.fg;
        // index 0 sits at the bottom of the stack.
        const top = total - (index + 1) * layerHeight - index * gap;
        return (
          <div
            key={layer}
            style={{
              position: "absolute",
              left: 0,
              top,
              width,
              height: layerHeight,
              boxSizing: "border-box",
              border: `${pack.stroke.hair + 1}px solid ${tone}`,
              borderLeft: `${pack.stroke.heavy}px solid ${tone}`,
              background: accent ? `${colors.accent}14` : "transparent",
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              gap: 20,
              padding: "0 28px",
              opacity: enter,
              transform: `translateY(${(1 - enter) * 28}px)`,
            }}
          >
            <span
              style={{
                fontFamily: pack.fonts.mono,
                fontSize: pack.type.label.lg,
                letterSpacing: "0.1em",
                textTransform: "uppercase",
                color: tone,
              }}
            >
              {layer}
            </span>
            {labels?.[index] ? (
              <span
                style={{
                  fontFamily: pack.fonts.mono,
                  fontSize: pack.type.label.sm,
                  letterSpacing: "0.12em",
                  color: colors.sub,
                  textAlign: "right",
                }}
              >
                {labels[index]}
              </span>
            ) : null}
          </div>
        );
      })}
    </div>
  );
};
