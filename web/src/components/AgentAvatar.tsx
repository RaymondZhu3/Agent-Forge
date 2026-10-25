import { useMemo } from "react";
import { hashStr } from "../lib/format";

/** Deterministic geometric identity from the agent id/name: a mirrored 5x5 grid on a gradient tile. */
export default function AgentAvatar({ seed, size = 40 }: { seed: string; size?: number }) {
  const { cells, h1, h2, gid } = useMemo(() => {
    const h = hashStr(seed || "agent");
    const hue = 150 + (h % 70); // ledger green → navy band
    const cells: [number, number][] = [];
    let bits = h ^ (hashStr(seed + "x") << 1);
    for (let y = 0; y < 5; y++) {
      for (let x = 0; x < 3; x++) {
        if (bits & 1) {
          cells.push([x, y]);
          if (x < 2) cells.push([4 - x, y]);
        }
        bits = (bits >>> 1) | ((bits & 1) << 30);
      }
    }
    return { cells, h1: hue, h2: hue + 40, gid: `av-${h.toString(36)}` };
  }, [seed]);

  return (
    <svg width={size} height={size} viewBox="0 0 40 40" role="img" aria-label="Agent avatar" className="avatar">
      <defs>
        <linearGradient id={gid} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor={`hsl(${h1} 45% 30%)`} />
          <stop offset="1" stopColor={`hsl(${h2} 40% 26%)`} />
        </linearGradient>
      </defs>
      <rect width="40" height="40" rx="8" fill="#f8faf6" />
      <rect x="0.5" y="0.5" width="39" height="39" rx="7.5" fill="none" stroke="#a9b9ac" />
      {cells.map(([x, y], i) => (
        <rect key={i} x={7 + x * 5.2} y={7 + y * 5.2} width="4.4" height="4.4" rx="1" fill={`url(#${gid})`} />
      ))}
    </svg>
  );
}
