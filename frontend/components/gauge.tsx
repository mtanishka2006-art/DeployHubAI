import * as React from "react";

function scoreColor(score: number): string {
  if (score >= 80) return "hsl(150 42% 70%)";
  if (score >= 60) return "hsl(40 90% 55%)";
  return "hsl(0 80% 60%)";
}

export function Gauge({
  value,
  label,
  size = 140,
  suffix = "",
}: {
  value: number;
  label?: string;
  size?: number;
  suffix?: string;
}) {
  const clamped = Math.max(0, Math.min(100, value));
  const stroke = 12;
  const radius = (size - stroke) / 2;
  const circ = 2 * Math.PI * radius;
  // 270-degree arc
  const arcFraction = 0.75;
  const dash = circ * arcFraction;
  const offset = dash * (1 - clamped / 100);
  const color = scoreColor(clamped);

  return (
    <div
      className="relative flex items-center justify-center"
      style={{ width: size, height: size }}
    >
      <svg width={size} height={size} className="rotate-[135deg]">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="hsl(var(--muted))"
          strokeWidth={stroke}
          strokeDasharray={`${dash} ${circ}`}
          strokeLinecap="round"
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={stroke}
          strokeDasharray={`${dash} ${circ}`}
          strokeDashoffset={offset}
          strokeLinecap="round"
          style={{ transition: "stroke-dashoffset 0.6s ease" }}
        />
      </svg>
      <div className="absolute flex flex-col items-center">
        <span
          className="text-3xl font-bold tabular-nums"
          style={{ color }}
        >
          {Math.round(clamped)}
          {suffix}
        </span>
        {label && (
          <span className="text-xs uppercase tracking-wide text-muted-foreground">
            {label}
          </span>
        )}
      </div>
    </div>
  );
}
