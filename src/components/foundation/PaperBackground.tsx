import { AbsoluteFill, useCurrentFrame, useVideoConfig } from "remotion";
import type { ReactNode } from "react";
import { useTheme } from "../../lib/theme";
import type { SurfaceName } from "../../packs/types";
import { Grain } from "./Grain";

/**
 * The paper (or night) surface every scene sits on: flat tone, soft vignette,
 * faint grain. Texture is deterministic — the same frame always looks the same.
 */
export const PaperBackground = ({
  children,
  surface,
}: {
  children?: ReactNode;
  surface?: SurfaceName;
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const { pack, colors } = useTheme();
  const activeSurface = surface ?? (colors.bg === pack.palette.night ? "night" : "paper");
  const surfaceColors = pack.surface[activeSurface];

  return (
    <AbsoluteFill style={{ backgroundColor: surfaceColors.bg }}>
      <AbsoluteFill
        style={{
          background: `radial-gradient(ellipse 78% 68% at 50% 46%, rgba(0,0,0,0) 42%, rgba(0,0,0,${
            pack.texture.vignette
          }) 100%)`,
        }}
      />
      <Grain opacity={pack.texture.grain} seed={11} driftFrames={frame} fps={fps} />
      {children}
    </AbsoluteFill>
  );
};
