"use client";

const BAR_COUNT = 24;

type AuraState = "speaking" | "listening" | "idle";

const SIZE_MAP: Record<string, number> = {
  sm: 64,
  md: 96,
  lg: 128,
  xl: 160,
};

interface AgentAudioVisualizerAuraProps {
  /** Named ("sm" | "md" | "lg" | "xl") or pixel size. */
  size?: string | number;
  /** Base color of the aura bars. */
  color?: string;
  /** Fraction (0..1) of a full hue rotation applied across the bars. */
  colorShift?: number;
  /** Voice assistant state driving the animation intensity. */
  state?: AuraState;
  /** Injected theme mode ("light" | "dark") used for idle transparency. */
  themeMode?: string | undefined;
  className?: string;
}

/**
 * Self-contained animated audio "aura" made of CSS-animated bars.
 * Driven only by props so it stays independent of any specific audio track.
 */
export function AgentAudioVisualizerAura({
  size = "md",
  color = "#1FD5F9",
  colorShift = 0,
  state = "idle",
  themeMode,
  className,
}: AgentAudioVisualizerAuraProps) {
  const px = typeof size === "number" ? size : (SIZE_MAP[size] ?? SIZE_MAP.md);
  const isDark = themeMode !== "light";
  const isActive = state === "speaking" || state === "listening";
  const idleOpacity = isDark ? 0.35 : 0.25;
  const hueStep = colorShift * 360;
  const animation = isActive ? "auva-aura-pop" : "auva-aura-idle";

  const barWidth = Math.max(2, px / BAR_COUNT / 2);

  return (
    <div
      className={className}
      style={{ position: "relative", width: px, height: px }}
      role="img"
      aria-label={
        state === "speaking"
          ? "L'assistant parle"
          : state === "listening"
          ? "L'assistant écoute"
          : "Assistant en attente"
      }
    >
      <style>{`
        @keyframes auva-aura-pop {
          0%, 100% { transform: scaleY(0.2); }
          50% { transform: scaleY(1); }
        }
        @keyframes auva-aura-idle {
          0%, 100% { transform: scaleY(0.3); }
          50% { transform: scaleY(0.55); }
        }
      `}</style>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          gap: Math.max(1, px / 60),
          width: "100%",
          height: "100%",
        }}
      >
        {Array.from({ length: BAR_COUNT }, (_, i) => i).map((i) => (
          <div
            key={i}
            style={{
              width: barWidth,
              height: "55%",
              background: color,
              filter: `hue-rotate(${hueStep * (i / BAR_COUNT)}deg) saturate(1.1)`,
              borderRadius: 9999,
              opacity: isActive ? 0.9 : idleOpacity,
              transform: "scaleY(0.3)",
              transformOrigin: "center",
              animation: `${animation} ${1.2 + (i % 7) * 0.14}s ease-in-out ${
                (i % 5) * -0.15
              }s infinite`,
            }}
          />
        ))}
      </div>
    </div>
  );
}