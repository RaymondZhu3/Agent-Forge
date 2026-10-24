import { useCallback, useEffect, useRef, useState } from "react";

export type Async<T> = { data: T | null; error: string | null; loading: boolean; reload: () => void };

/** Fetch on mount / when deps change; keeps previous data visible while refreshing. */
export function useAsync<T>(fn: () => Promise<T>, deps: unknown[]): Async<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);
  const fnRef = useRef(fn);
  fnRef.current = fn;

  useEffect(() => {
    let alive = true;
    setLoading(true);
    fnRef.current().then(
      (d) => {
        if (alive) {
          setData(d);
          setError(null);
          setLoading(false);
        }
      },
      (e: Error) => {
        if (alive) {
          setError(e.message);
          setLoading(false);
        }
      },
    );
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);

  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { data, error, loading, reload };
}

export function useDocumentTitle(title: string) {
  useEffect(() => {
    document.title = `${title} · Agent Forge`;
  }, [title]);
}

export function useMediaQuery(q: string): boolean {
  const [m, setM] = useState(() => window.matchMedia(q).matches);
  useEffect(() => {
    const mq = window.matchMedia(q);
    const on = () => setM(mq.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, [q]);
  return m;
}
