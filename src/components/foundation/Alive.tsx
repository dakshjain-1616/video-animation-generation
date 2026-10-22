import { useCurrentFrame, useVideoConfig } from "remotion";
import type { ReactNode } from "react";

/**
 * Alive: a subtle continuous motion layer for a scene's main visual.
 *
 * Entrance animations settle; this keeps one thing moving afterward, which is
 * what separates a motion graphic from a slide. It wraps children in a
 * full-frame layer and applies a slow drift, breath or orbit. The motion gate
 * measures the difference between the midpoint and 85% of the scene, so a scene
 * that stops moving is repaired.
 */
export const Alive = ({
  children,
  mode = "drift",
  amplitude = 7,
  period = 4.5,
  delay = 0,
}: {
  children: ReactNode;
  mode?: "drift" | "breathe" | "orbit";
  /** Pixels (drift/orbit) or scale delta (breathe). */
  amplitude?: number;
  /** Seconds for one full cycle. */
  period?: number;
  delay?: number;
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = (frame - delay * fps) / (period * fps);
  const angle = t * Math.PI * 2;
  const transform =
    mode === "breathe"
      ? `scale(${1 + Math.sin(angle) * (amplitude / 100)})`
      : mode === "orbit"
        ? `translate(${Math.cos(angle) * amplitude}px, ${Math.sin(angle) * amplitude}px)`
        : `translate(${Math.sin(angle) * amplitude}px, ${Math.cos(angle * 0.7) * amplitude * 0.6}px)`;

  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        transform,
        transformOrigin: "50% 50%",
      }}
    >
      {children}
    </div>
  );
};
