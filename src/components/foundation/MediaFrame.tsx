import { useState } from "react";
import { AnimatedImage, Img, OffthreadVideo, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { useTheme } from "../../lib/theme";
import { enterProgress } from "../../lib/motion";

/**
 * MediaFrame: a caller-provided image or video, mounted as a paper object.
 *
 * The artifact is the protagonist of a media scene: framed in chalk with a
 * hairline ink border and a mono caption bar. The media is never redrawn or
 * restyled — it is shown as-is, fitted (letterboxed) inside a fixed box so the
 * layout never depends on the file's aspect ratio. Videos render muted.
 */
export const MEDIA_ANIMATION_RE = /\.(gif|webp)$/i;
export const MEDIA_VIDEO_RE = /\.(mp4|webm|mov)$/i;

export const MediaFrame = ({
  asset,
  caption,
  source,
  x,
  y,
  width,
  height,
  startAt = 0,
  tilt = 0,
  delay = 0,
}: {
  /** Exact staged filename string from the brief (e.g. "generated/p_x/tweet-1.png"). */
  asset: string;
  caption?: string;
  source?: string;
  x: number;
  y: number;
  width: number;
  height: number;
  /** Seconds into the clip to start from (video assets only). */
  startAt?: number;
  tilt?: number;
  delay?: number;
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const { pack } = useTheme();
  const [failed, setFailed] = useState(false);
  const enter = enterProgress(frame, fps, delay, 0.55);
  const isVideo = MEDIA_VIDEO_RE.test(asset);
  const startFrom = Math.max(0, Math.round(startAt * fps));

  return (
    <div
      style={{
        position: "absolute",
        left: x,
        top: y,
        width,
        height,
        opacity: enter,
        transform: `rotate(${tilt}deg) translateY(${(1 - enter) * 12}px)`,
      }}
    >
      <div
        style={{
          position: "absolute",
          inset: 0,
          background: pack.palette.chalk,
          border: `${pack.stroke.hair}px solid ${pack.palette.ink}`,
          boxShadow: `8px 10px 0 rgba(0,0,0,0.18)`,
        }}
      >
        <div
          style={{
            position: "absolute",
            left: pack.stroke.regular,
            right: pack.stroke.regular,
            top: pack.stroke.regular,
            bottom: captionBarHeight(caption, source),
            overflow: "hidden",
            background: pack.palette.fill,
          }}
        >
          {failed ? (
            <div
              style={{
                width: "100%",
                height: "100%",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                padding: 24,
                fontFamily: pack.fonts.mono,
                fontSize: pack.type.label.md,
                letterSpacing: "0.16em",
                textAlign: "center",
                color: pack.palette.muted,
              }}
            >
              ARTIFACT UNAVAILABLE
            </div>
          ) : isVideo ? (
            <OffthreadVideo
              muted
              src={staticFile(asset)}
              startFrom={startFrom}
              onError={() => setFailed(true)}
              style={{ width: "100%", height: "100%", objectFit: "contain" }}
            />
          ) : MEDIA_ANIMATION_RE.test(asset) ? (
            <AnimatedImage
              src={staticFile(asset)}
              width={Math.max(1, width - pack.stroke.regular * 2)}
              height={Math.max(1, height - pack.stroke.regular - captionBarHeight(caption, source))}
              fit="contain"
            />
          ) : (
            <Img
              src={staticFile(asset)}
              onError={() => setFailed(true)}
              style={{ width: "100%", height: "100%", objectFit: "contain" }}
            />
          )}
        </div>
      </div>
      {caption ? (
        <div
          style={{
            position: "absolute",
            left: 0,
            right: 0,
            bottom: 0,
            height: captionBarHeight(caption, source),
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 16,
            paddingLeft: 18,
            paddingRight: 18,
            fontFamily: pack.fonts.mono,
            fontSize: pack.type.label.sm,
            letterSpacing: "0.14em",
            textTransform: "uppercase",
            whiteSpace: "nowrap",
            overflow: "hidden",
          }}
        >
          <span style={{ color: pack.palette.ink, overflow: "hidden", textOverflow: "ellipsis" }}>{caption}</span>
          {source ? <span style={{ color: pack.palette.muted }}>{source}</span> : null}
        </div>
      ) : null}
    </div>
  );
};

const captionBarHeight = (caption?: string, _source?: string): number => (caption ? 46 : 0);
