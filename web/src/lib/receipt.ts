/* Audit receipts, browser side of server/runtime/receipt.py. Must produce byte-identical canonical JSON:
   sorted keys, no whitespace, JS number formatting (Python mimics it), non-ASCII kept as-is. */
import type { Run, RunStep } from "../types";

const VERSION = "agentforge-receipt-v1";

export function canonical(v: unknown): string {
  if (v === null || v === undefined) return "null";
  if (typeof v === "boolean") return v ? "true" : "false";
  if (typeof v === "number") {
    if (!Number.isFinite(v)) throw new Error("non-finite number in receipt data");
    return String(v);
  }
  if (typeof v === "string") return JSON.stringify(v);
  if (Array.isArray(v)) return "[" + v.map(canonical).join(",") + "]";
  if (typeof v === "object") {
    const o = v as Record<string, unknown>;
    return "{" + Object.keys(o).sort().map((k) => JSON.stringify(k) + ":" + canonical(o[k])).join(",") + "}";
  }
  return canonical(String(v));
}

/* ---- SHA-256: Web Crypto when available (secure contexts), else a small pure implementation ---- */
const K = new Uint32Array([
  0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5, 0xd807aa98, 0x12835b01,
  0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc,
  0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da, 0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147,
  0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
  0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070, 0x19a4c116, 0x1e376c08,
  0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3, 0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
  0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
]);

function sha256Pure(bytes: Uint8Array): string {
  const l = bytes.length, bitLen = l * 8;
  const n = (((l + 9) >> 6) + 1) << 6;
  const m = new Uint8Array(n);
  m.set(bytes);
  m[l] = 0x80;
  const dv = new DataView(m.buffer);
  dv.setUint32(n - 4, bitLen >>> 0);
  dv.setUint32(n - 8, Math.floor(bitLen / 2 ** 32));
  const H = new Uint32Array([0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19]);
  const W = new Uint32Array(64);
  const rotr = (x: number, r: number) => (x >>> r) | (x << (32 - r));
  for (let off = 0; off < n; off += 64) {
    for (let i = 0; i < 16; i++) W[i] = dv.getUint32(off + i * 4);
    for (let i = 16; i < 64; i++) {
      const s0 = rotr(W[i - 15], 7) ^ rotr(W[i - 15], 18) ^ (W[i - 15] >>> 3);
      const s1 = rotr(W[i - 2], 17) ^ rotr(W[i - 2], 19) ^ (W[i - 2] >>> 10);
      W[i] = (W[i - 16] + s0 + W[i - 7] + s1) >>> 0;
    }
    let [a, b, c, d, e, f, g, h] = H;
    for (let i = 0; i < 64; i++) {
      const t1 = (h + (rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25)) + ((e & f) ^ (~e & g)) + K[i] + W[i]) >>> 0;
      const t2 = ((rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22)) + ((a & b) ^ (a & c) ^ (b & c))) >>> 0;
      h = g; g = f; f = e; e = (d + t1) >>> 0; d = c; c = b; b = a; a = (t1 + t2) >>> 0;
    }
    H[0] += a; H[1] += b; H[2] += c; H[3] += d; H[4] += e; H[5] += f; H[6] += g; H[7] += h;
  }
  return Array.from(H, (x) => x.toString(16).padStart(8, "0")).join("");
}

export async function sha256(s: string): Promise<string> {
  const bytes = new TextEncoder().encode(s);
  const subtle = (globalThis as { crypto?: Crypto }).crypto?.subtle;
  if (subtle) {
    const buf = await subtle.digest("SHA-256", bytes);
    return Array.from(new Uint8Array(buf), (b) => b.toString(16).padStart(2, "0")).join("");
  }
  return sha256Pure(bytes);
}

type Receipt = { version: number; algo: string; hash: string; steps: string[]; sig?: string; key_id?: string };

function stepRecord(s: RunStep) {
  let out = s.output as Record<string, unknown> | null;
  if (out && typeof out === "object" && !Array.isArray(out) && "receipt" in out) {
    const { receipt: _r, ...rest } = out;
    out = rest;
  }
  return { step: s.step, type: s.type, tool: s.toolName ?? null, input: s.input ?? null, output: out ?? null, success: s.success !== false, error: s.error ?? null };
}

/** The receipt a run's final verify step stored, if any. */
export function receiptOf(steps: RunStep[] | null | undefined): Receipt | null {
  for (let i = (steps?.length ?? 0) - 1; i >= 0; i--) {
    const r = (steps![i].output as { receipt?: Receipt } | null)?.receipt;
    if (r && typeof r.hash === "string") return r;
  }
  return null;
}

export type ReceiptCheck = { ok: boolean; reason: string; steps: number; badIndex?: number };

/** Recompute a stored run's chain (GET /api/runs/{id}) and compare with its receipt. */
export async function verifyRun(run: Run): Promise<ReceiptCheck> {
  const steps = run.steps ?? [];
  let idx = -1;
  for (let i = steps.length - 1; i >= 0; i--) if ((steps[i].output as { receipt?: unknown } | null)?.receipt) { idx = i; break; }
  if (idx < 0) return { ok: false, reason: "This run has no receipt.", steps: 0 };
  const stored = (steps[idx].output as { receipt: Receipt }).receipt;
  let h = await sha256(VERSION + "\n" + canonical({ run_id: run.id, agent_id: run.agent_id, user_message: run.user_message }));
  const links: string[] = [];
  for (const s of steps.slice(0, idx + 1)) {
    h = await sha256(h + "\n" + canonical(stepRecord(s)));
    links.push(h);
  }
  const final = await sha256(h + "\n" + canonical({ answer: run.assistant_message ?? "" }));
  if (final === stored.hash) return { ok: true, reason: `The record is intact. All ${idx + 1} steps and the answer match the receipt.`, steps: idx + 1 };
  const bad = links.findIndex((x, i) => x !== stored.steps?.[i]);
  return { ok: false, reason: bad >= 0 ? `Record changed at step ${steps[bad].step}.` : "The answer was changed after the run.", steps: idx + 1, badIndex: bad >= 0 ? bad : links.length };
}
