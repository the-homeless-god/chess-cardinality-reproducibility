"""Collect exact April labels only after both policy predictions are frozen."""

from __future__ import annotations

import csv
import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import chess

ROOT = Path(__file__).parent
INPUT = ROOT / "data/endgame_corpus_2025_04/positions.csv"
PREDICTIONS = ROOT / "results_scenarios_2025_04/predictions.json"
PREDICTION_MANIFEST = ROOT / "results_scenarios_2025_04/prediction_manifest.json"
OUTPUT = ROOT / "results_scenarios_2025_04"
ENDPOINT = "https://tablebase.lichess.ovh/standard"


def query(fen: str) -> dict:
    url = ENDPOINT + "?" + urllib.parse.urlencode({"fen": fen})
    request = urllib.request.Request(
        url, headers={"User-Agent": "phd-chess-cardinality-research/1.0"}
    )
    for retry in range(3):
        try:
            with urllib.request.urlopen(request, timeout=25) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            if error.code != 429 or retry == 2:
                raise
            time.sleep(60)
        except (TimeoutError, urllib.error.URLError):
            if retry == 2:
                raise
            time.sleep(5)
    raise AssertionError("unreachable")


def main() -> None:
    frozen = json.loads(PREDICTION_MANIFEST.read_text())
    assert frozen["labels_used"] is False
    assert hashlib.sha256(PREDICTIONS.read_bytes()).hexdigest() == frozen["predictions_sha256"]
    assert hashlib.sha256(INPUT.read_bytes()).hexdigest() == frozen["positions_sha256"]
    with INPUT.open(newline="") as handle:
        positions = list(csv.DictReader(handle))
    predictions = json.loads(PREDICTIONS.read_text())
    assert [x["position_id"] for x in positions] == [x["position_id"] for x in predictions]
    path = OUTPUT / "responses.jsonl"
    existing = {}
    if path.exists():
        for line in path.read_text().splitlines():
            record = json.loads(line)
            existing[record["position_id"]] = record
    with path.open("a") as handle:
        for index, row in enumerate(positions):
            if row["position_id"] in existing:
                continue
            if index:
                time.sleep(1.2)
            board = chess.Board(row["fen"])
            response = query(row["fen"])
            if response["category"] == "unknown":
                raise ValueError(row["position_id"])
            if {m.uci() for m in board.legal_moves} != {m["uci"] for m in response["moves"]}:
                raise ValueError(f"move mismatch {row['position_id']}")
            record = {"position_id": row["position_id"], "fen": row["fen"], "response": response}
            handle.write(json.dumps(record, sort_keys=True) + "\n")
            handle.flush()
            existing[row["position_id"]] = record
            if len(existing) % 10 == 0:
                print(f"{len(existing)}/{len(positions)} April positions", flush=True)
    assert len(existing) == len(positions) == 250
    manifest = {
        "protocol": "scenario-comparison-protocol-v1",
        "endpoint": ENDPOINT,
        "positions_sha256": hashlib.sha256(INPUT.read_bytes()).hexdigest(),
        "predictions_sha256_before_labels": frozen["predictions_sha256"],
        "responses_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "positions": len(positions), "delay_seconds": 1.2,
    }
    (OUTPUT / "response_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
