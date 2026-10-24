import { Activity, LayoutGrid, PenTool, Radio } from "lucide-react";
import { NavLink, Outlet } from "react-router-dom";
import { api } from "../lib/api";
import { useAsync } from "../lib/hooks";

function Logo() {
  return (
    <svg width="26" height="26" viewBox="0 0 32 32" aria-hidden>
      <defs>
        <linearGradient id="lg" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#6b9bff" />
          <stop offset="1" stopColor="#a479ff" />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="7" fill="#0e1226" stroke="#2a3260" />
      <path d="M9 22 16 8l7 14h-4l-3-6-3 6z" fill="url(#lg)" />
    </svg>
  );
}

const NAV = [
  { to: "/", label: "Agents", icon: LayoutGrid, end: true },
  { to: "/builder", label: "Builder", icon: PenTool, end: false },
  { to: "/dashboard", label: "Observability", icon: Activity, end: false },
];

function HealthDot() {
  const { data, error } = useAsync(() => api.health(), []);
  const state = error ? "down" : !data ? "wait" : data.ok ? "up" : "down";
  const label = state === "up" ? "API online" : state === "down" ? "API unreachable" : "Connecting…";
  return (
    <div className="health" title={data ? `DB ${data.db ? "ok" : "down"} · Gemini ${data.gemini ? "key set" : "missing"} · SerpApi ${data.serpapi} · Nessie ${data.nessie}` : undefined}>
      <span className={`dot ${state}`} />
      <div>
        <div className="health-t">{label}</div>
        {data && (
          <div className="health-s mono">
            serpapi:{data.serpapi} · nessie:{data.nessie}
          </div>
        )}
      </div>
    </div>
  );
}

export default function Shell() {
  return (
    <div className="shell">
      <aside className="side">
        <NavLink to="/" className="brand" aria-label="Agent Forge home">
          <Logo />
          <span>Agent Forge</span>
        </NavLink>
        <nav aria-label="Main">
          {NAV.map((n) => (
            <NavLink key={n.to} to={n.to} end={n.end} className={({ isActive }) => `nav-item${isActive ? " active" : ""}`}>
              <n.icon size={16} />
              <span>{n.label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="side-foot">
          <div className="tagline">
            <Radio size={12} /> Other platforms help you build agents. We help you trust them.
          </div>
          <HealthDot />
        </div>
      </aside>
      <main className="main">
        <Outlet />
      </main>
    </div>
  );
}
