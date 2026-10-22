import { useCurrentFrame, useVideoConfig } from "remotion";
import { AbsoluteFill } from "remotion";
import { useTheme } from "../../lib/theme";
import { clamp01, easeInOutCubic } from "../../lib/motion";

/**
 * "Paper dip" transition: the frame opens from flat paper, or closes to it.
 * Cheaper and calmer than a wipe, and it matches the reference's hard-cut feel.
 */
export const PaperDip = ({
  mode = "in",
  duration = 0.45,
}: {
  mode?: "in" | "out";
  duration?: number;
}) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();
  const { colors } = useTheme();
  const length = Math.max(1, duration * fps);
  // "in" counts from the scene's first frame, "out" toward its last.
  const t = clamp01(mode === "in" ? frame / length : (frame - (durationInFrames - length)) / length);
  const eased = easeInOutCubic(t);
  const opacity = mode === "in" ? 1 - eased : eased;

  return (
    <AbsoluteFill
      style={{ backgroundColor: colors.bg, opacity, pointerEvents: "none" }}
    />
  );
};
