#!/usr/bin/env python3
"""Cron pre-run script for Hermes daily briefing.

Runs the venv-backed collector, stores the full JSON artifact, then prints a compact
candidate list to stdout so the LLM can select and summarize from grounded inputs.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path("/workspace/daily-briefing")
OUTPUT = ROOT / "output" / "candidates.cron.json"


def main() -> int:
    cmd = [
        str(ROOT / "bin" / "collect-candidates"),
        "--days", "1",
        "--per-category", "10",
        "--output", str(OUTPUT),
    ]
    run = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, timeout=300)
    if run.returncode != 0:
        print("COLLECTOR_FAILED", file=sys.stderr)
        print(run.stdout, file=sys.stderr)
        print(run.stderr, file=sys.stderr)
        return run.returncode

    data = json.loads(OUTPUT.read_text(encoding="utf-8"))
    compact = {
        "collector_artifact": str(OUTPUT),
        "generated_at": data.get("generated_at"),
        "window_days": data.get("window_days"),
        "source_errors": data.get("source_errors", []),
        "candidates": {},
    }
    for category, items in data.get("candidates", {}).items():
        compact["candidates"][category] = []
        for item in items:
            compact["candidates"][category].append({
                "title": item.get("title"),
                "url": item.get("url"),
                "source": item.get("source"),
                "published_at": item.get("published_at"),
                "summary": item.get("summary"),
                "score": item.get("score"),
                "date_status": item.get("date_status"),
                "extracted_excerpt": (item.get("extracted_text") or "")[:1200],
                "fetch_errors": item.get("errors", []),
            })
    print("RSS_COLLECTOR_CONTEXT_JSON_START")
    print(json.dumps(compact, ensure_ascii=False, indent=2))
    print("RSS_COLLECTOR_CONTEXT_JSON_END")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
