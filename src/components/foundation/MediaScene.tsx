import type { ReactNode } from "react";
import { useStage, type Stage } from "../../lib/stage";
import type { SurfaceName } from "../../packs/types";
import { KineticHeading } from "./KineticHeading";
import { MediaFrame } from "./MediaFrame";
import { MonoLabel } from "./MonoLabel";
import { SceneShell } from "./SceneShell";
import { SectionHeader } from "./SectionHeader";

export type MediaLayout = {
  /** The framed artifact: always the dominant object on the stage. */
  media: { x: number; y: number; width: number; height: number };
  /** Where a short annotation or display line belongs. */
  note: { x: number; y: number; width: number; height: number };
};

/**
 * Deterministic media composition. In portrait the artifact fills the upper
 * visual box and the note sits below; in landscape it takes the left two
 * thirds and the note column is on the right. Generated code can call this to
 * place a FocusPin or LeaderLine against the real media rectangle.
 */
export const mediaLayout = (stage: Stage): MediaLayout => {
  const v = stage.visual;
  if (stage.portrait) {
    const height = v.height * 0.58;
    return {
      media: { x: v.x, y: v.y, width: v.width, height },
      note: { x: v.x, y: v.y + height + 28, width: v.width, height: v.height - height - 28 },
    };
  }
  const width = v.width * 0.64;
  return {
    media: { x: v.x, y: v.y + v.height * 0.04, width, height: v.height * 0.92 },
    note: { x: v.x + width + 32, y: v.y + 40, width: v.width - width - 32, height: v.height - 80 },
  };
};

/**
 * MediaScene: the house layout for a scene anchored on caller media.
 *
 * The artifact is the protagonist by construction: its box is computed from
 * the stage instead of left to the model. Keep custom overlays (FocusPin,
 * LeaderLine) inside mediaLayout(stage).media, and put display copy in the
 * note area or pass it as `note`.
 */
export const MediaScene = ({
  index,
  kicker,
  lines,
  surface = "paper",
  asset,
  caption,
  source,
  startAt,
  tilt,
  note,
  children,
}: {
  index: string;
  kicker: string;
  lines: string[];
  surface?: SurfaceName;
  asset: string;
  caption?: string;
  source?: string;
  startAt?: number;
  tilt?: number;
  note?: string;
  /** Optional absolute-positioned overlays, e.g. FocusPin/LeaderLine/Arrow. */
  children?: ReactNode;
}) => {
  const stage = useStage();
  const layout = mediaLayout(stage);
  return (
    <SceneShell surface={surface}>
      <SectionHeader index={index} title={kicker} x={stage.left} y={stage.top} />
      <KineticHeading size="md" lines={lines} x={stage.left} y={stage.top + 56} />
      <MediaFrame
        asset={asset}
        caption={caption}
        source={source}
        startAt={startAt}
        tilt={tilt}
        x={layout.media.x}
        y={layout.media.y}
        width={layout.media.width}
        height={layout.media.height}
      />
      {note ? (
        <MonoLabel x={layout.note.x} y={layout.note.y} size="md" color="ink">
          {note}
        </MonoLabel>
      ) : null}
      {children}
    </SceneShell>
  );
};
