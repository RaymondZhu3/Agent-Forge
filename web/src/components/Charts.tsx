import { useMemo, useState } from "react";
import { fmtTime } from "../lib/format";
import type { AnalyticsSummary, ToolAnalytics } from "../types";
import ToolIcon from "./ToolIcon";

type Point = AnalyticsSummary["runs_over_time"][number];

/** Hourly stacked bars (completed + failed). Hover or focus a bar for exact counts. */
export function RunsChart({ points }: { points: Point[] }) {
  const [hover, setHover] = useState<number | null>(null);
  const W = 640, H = 220, padL = 34, padR = 8, padT = 12, padB = 26;
  const data = useMemo(() => {
    // fill empty hours between first and last bucket so gaps are visible, not hidden
    if (!points.length) return [];
    const byTs = new Map(points.map((p) => [new Date(p.bucket).getTime(), p]));
    const ts = [...byTs.keys()].sort((a, b) => a - b);
    const out: Point[] = [];
    for (let t = ts[0]; t <= ts[ts.length - 1]; t += 3600_000) out.push(byTs.get(t) ?? { bucket: new Date(t).toISOString(), runs: 0, failed: 0 });
    return out.slice(-48);
  }, [points]);

  const max = Math.max(1, ...data.map((d) => d.runs));
  const niceMax = max <= 4 ? 4 : Math.ceil(max / 4) * 4;
  const innerW = W - padL - padR, innerH = H - padT - padB;
  const bw = data.length ? innerW / data.length : innerW;
  const y = (v: number) => padT + innerH - (v / niceMax) * innerH;
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => Math.round(niceMax * f));
  const every = Math.max(1, Math.ceil(data.length / 6));

  return (
    <div className="chart">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Runs per hour" preserveAspectRatio="none">
        <defs>
          <linearGradient id="barg" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#1d2b45" />
            <stop offset="1" stopColor="#1d2b45" />
          </linearGradient>
        </defs>
        {ticks.map((t, i) => (
          <g key={i}>
            <line x1={padL} x2={W - padR} y1={y(t)} y2={y(t)} className="grid" />
            <text x={padL - 6} y={y(t) + 3} textAnchor="end" className="axis">{t}</text>
          </g>
        ))}
        {data.map((d, i) => {
          const x = padL + i * bw + bw * 0.18;
          const w = bw * 0.64;
          const ok = d.runs - d.failed;
          return (
            <g key={d.bucket} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)} onFocus={() => setHover(i)} onBlur={() => setHover(null)} tabIndex={0}
               aria-label={`${fmtTime(d.bucket)}: ${d.runs} runs, ${d.failed} failed`} className="bar-g">
              <rect x={padL + i * bw} y={padT} width={bw} height={innerH} fill="transparent" />
              {ok > 0 && <rect x={x} y={y(ok)} width={w} height={(ok / niceMax) * innerH} rx="1.5" fill="url(#barg)" className="grow" style={{ animationDelay: `${i * 18}ms` }} />}
              {d.failed > 0 && <rect x={x} y={y(d.runs)} width={w} height={(d.failed / niceMax) * innerH} rx="1.5" fill="#c81d25" className="grow" />}
              {i % every === 0 && (
                <text x={x + w / 2} y={H - 8} textAnchor="middle" className="axis">{fmtTime(d.bucket)}</text>
              )}
            </g>
          );
        })}
      </svg>
      {hover !== null && data[hover] && (
        <div className="tooltip" style={{ left: `${((padL + hover * bw + bw / 2) / W) * 100}%` }}>
          <strong>{new Date(data[hover].bucket).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric" })}</strong>
          <span>{data[hover].runs} runs</span>
          {data[hover].failed > 0 && <span className="err-t">{data[hover].failed} failed</span>}
        </div>
      )}
    </div>
  );
}

export function ToolBars({ stats }: { stats: ToolAnalytics[] }) {
  const max = Math.max(1, ...stats.map((s) => s.calls));
  return (
    <ul className="toolbars">
      {stats.map((s) => (
        <li key={s.tool_name}>
          <div className="tb-head">
            <ToolIcon name={s.tool_name} size={12} />
            <span className="mono">{s.tool_name}</span>
            <span className="mono tb-count">{s.calls}</span>
          </div>
          <div className="tb-track" role="img" aria-label={`${s.calls} calls, ${s.errors} errors`}>
            <span className="tb-fill" style={{ width: `${(s.calls / max) * 100}%` }} />
            {s.errors > 0 && <span className="tb-err" style={{ width: `${(s.errors / max) * 100}%` }} />}
          </div>
          <div className="tb-sub mono">
            avg {s.avg_ms === null ? "—" : `${Math.round(s.avg_ms)} ms`}
            {s.errors > 0 && <span className="err-t"> · {s.errors} errors</span>}
            {s.cache_hits > 0 && <span> · {s.cache_hits} cached</span>}
            {s.fixture_calls > 0 && <span className="warn-t"> · {s.fixture_calls} demo</span>}
          </div>
        </li>
      ))}
    </ul>
  );
}
