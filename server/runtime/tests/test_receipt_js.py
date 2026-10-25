"""The browser's receipt check (web/src/lib/receipt.ts) agrees with Python's, byte for byte.
Skipped if Node or the web app's esbuild isn't installed."""

from __future__ import annotations

import copy
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from server.runtime.tests.test_receipt import run_once, stored_run

ROOT = Path(__file__).resolve().parents[3]
ESBUILD = ROOT / "web" / "node_modules" / ".bin" / "esbuild"

HARNESS = r"""
import { verifyRun, canonical } from "./receipt.mjs";
import fs from "node:fs";
const runs = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const out = { subtle: [], pure: [], canon: canonical({ b: [1, 2.5, null, true, 1e-7, 0.00001, 1.5e22], a: "é\n\"x\"" }) };
for (const r of runs) out.subtle.push(await verifyRun(r));
Object.defineProperty(globalThis, "crypto", { value: undefined, configurable: true });
for (const r of runs) out.pure.push(await verifyRun(r));
console.log(JSON.stringify(out));
"""


@pytest.mark.skipif(not (shutil.which("node") and ESBUILD.exists()), reason="needs node + web/node_modules")
def test_browser_and_python_receipts_agree(tmp_path):
    r, hooks = run_once()
    good = stored_run(r, hooks)
    bad = copy.deepcopy(good)
    bad["steps"][1]["output"]["summary"] = "tampered"
    (tmp_path / "runs.json").write_text(json.dumps([good, bad]), encoding="utf-8")
    subprocess.run([str(ESBUILD), str(ROOT / "web/src/lib/receipt.ts"), "--format=esm", "--log-level=error",
                    f"--outfile={tmp_path / 'receipt.mjs'}"], check=True)
    (tmp_path / "h.mjs").write_text(HARNESS, encoding="utf-8")
    res = json.loads(subprocess.run(["node", str(tmp_path / "h.mjs"), str(tmp_path / "runs.json")],
                                    check=True, capture_output=True, text=True).stdout)
    for mode in ("subtle", "pure"):
        assert res[mode][0]["ok"], res[mode][0]
        assert not res[mode][1]["ok"] and "step 2" in res[mode][1]["reason"]
    from server.runtime.receipt import canonical
    assert res["canon"] == canonical({"b": [1, 2.5, None, True, 1e-7, 0.00001, 1.5e22], "a": "é\n\"x\""})
