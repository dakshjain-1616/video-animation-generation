import { spring, useCurrentFrame, useVideoConfig } from "remotion";
import { useTheme } from "../../lib/theme";

/**
 * FocusPin: an accent highlight that springs in over the region of the media
 * the scene is talking about — the "look here" moment. Pure overlay; it
 * annotates the artifact, it never replaces it.
 */
export const FocusPin = ({
  x,
  y,
  width,
  height,
  delay = 0,
  rounded = 14,
}: {
  x: number;
  y: number;
  width: number;
  height: number;
  delay?: number;
  rounded?: number;
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const { colors } = useTheme();
  const pop = spring({
    frame: frame - delay * fps,
    fps,
    config: { damping: 12, stiffness: 140, mass: 0.6 },
  });
  const scale = 0.7 + 0.3 * pop;

  return (
    <div
      style={{
        position: "absolute",
        left: x,
        top: y,
        width,
        height,
        borderRadius: rounded,
        border: `${3}px solid ${colors.accent}`,
        boxShadow: `0 0 0 ${6}px ${colors.accent}22`,
        opacity: Math.min(1, pop),
        transform: `scale(${scale})`,
      }}
    />
  );
};
