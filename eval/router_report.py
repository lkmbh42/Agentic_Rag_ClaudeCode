"""Router metrics over the labeled set (Phase 3).

Runs the real IntentRouter (classification model from settings) over
eval/router_labeled.jsonl and prints accuracy, per-intent recall, latency
percentiles, and every miss — as JSON. Used to fill the Phase 3 report and
re-run at GPU provisioning (vLLM latency gate: p95 <= 400 ms).

Run INSIDE the backend container (needs app deps + the compose network):
  docker compose -f docker-compose.dev.yml exec -T backend \
      python /srv/eval/router_report.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, "/srv")

from app.config import get_settings  # noqa: E402
from app.router import IntentRouter  # noqa: E402


def pctl(vals: list[float], p: float) -> float:
    vals = sorted(vals)
    return round(vals[min(len(vals) - 1, int(round(p * (len(vals) - 1))))], 1)


def main() -> None:
    labeled = Path(__file__).resolve().parent / "router_labeled.jsonl"
    rows = [json.loads(ln) for ln in labeled.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.startswith("#")]

    router = IntentRouter()
    misses, lat = [], []
    per_intent: dict[str, dict[str, int]] = {}
    for row in rows:
        d = router.classify(row["query"])
        lat.append(d.latency_ms)
        stats = per_intent.setdefault(row["intent"], {"n": 0, "correct": 0})
        stats["n"] += 1
        if d.intent == row["intent"]:
            stats["correct"] += 1
        else:
            misses.append({"id": row["id"], "expected": row["intent"],
                           "got": d.intent, "source": d.source})

    settings = get_settings()
    print(json.dumps({
        "backend": settings.llm_backend,
        "model": settings.llm_class_model,
        "cases": len(rows),
        "accuracy": round(1 - len(misses) / len(rows), 4),
        "per_intent_recall": {k: round(v["correct"] / v["n"], 4)
                              for k, v in sorted(per_intent.items())},
        "latency_ms": {"p50": pctl(lat, 0.5), "p95": pctl(lat, 0.95),
                       "max": round(max(lat), 1)},
        "misses": misses,
    }, indent=2))


if __name__ == "__main__":
    main()
