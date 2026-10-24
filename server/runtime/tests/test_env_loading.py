"""Live bug: GEMINI_MODEL in .env was ignored by the CLI because llm.py read it before .env was loaded."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_cli_templates_use_gemini_model_from_dotenv(tmp_path):
    for d in ("server", "tools"):
        shutil.copytree(ROOT / d, tmp_path / d, ignore=shutil.ignore_patterns("__pycache__", ".cache"))
    (tmp_path / ".env").write_text("GEMINI_MODEL=gemini-from-dotenv\n")
    env = {k: v for k, v in os.environ.items() if not k.startswith("GEMINI_")}
    out = subprocess.run(
        [sys.executable, "-c", "import server.runtime.cli as c; print(c.TEMPLATES[0].model)"],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=60,
    )
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "gemini-from-dotenv"
