"""Explicit real-data integration script; not a synthetic product demonstration.

Run after training and starting uvicorn on localhost:8026:
    python tests/smoke_live_api.py
"""
import json
import time
from pathlib import Path

import httpx

root = Path(__file__).resolve().parents[1]
request = json.loads((root / "examples/real_match_replay.json").read_text())
with httpx.Client(base_url="http://127.0.0.1:8026", timeout=60, trust_env=False) as client:
    health = client.get("/health")
    health.raise_for_status()
    started = time.perf_counter()
    response = client.post("/predict", json=request)
    elapsed = time.perf_counter() - started
    response.raise_for_status()
    body = response.json()
    assert abs(body["blue_win_probability"] + body["red_win_probability"] - 1) < 1e-12
    assert "test" not in body["training_samples"]
    lookup = client.get("/players", params={"query": "Faker", "as_of": request["as_of"]})
    lookup.raise_for_status()
    invalid = dict(request, as_of="2025-01-01T00:00:00Z", scheduled_start="2025-01-01T00:00:00Z")
    rejection = client.post("/predict", json=invalid)
    assert rejection.status_code == 422
    result = {"health": health.json(), "predict_http_status": response.status_code,
              "elapsed_seconds": elapsed, "request_path": "examples/real_match_replay.json",
              "response": body, "past_model_rejection_status": rejection.status_code,
              "player_lookup": lookup.json()}
    (root / "reports/api_smoke.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": response.status_code, "seconds": elapsed,
                      "blue_probability": body["blue_win_probability"], "model": body["model_version"],
                      "invalid_as_of_status": rejection.status_code}))
