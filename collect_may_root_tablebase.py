"""Probe May roots after the full-game matches for diagnostic stratification."""

from __future__ import annotations

import csv
import hashlib
import json
import time
from pathlib import Path

import chess

from collect_endgame_tablebase import query

ROOT = Path(__file__).parent
INPUT = ROOT / "data/endgame_corpus_2025_05_games/positions.csv"
OUT = ROOT / "results_full_game_runtime"
DELAY_SECONDS = 1.2


def main() -> None:
    games_path = OUT / "games.jsonl"
    if not games_path.exists() or len(games_path.read_text().splitlines()) != 400:
        raise ValueError("Full-game predictions must be complete before root probes")
    with INPUT.open(newline="") as stream:
        positions = list(csv.DictReader(stream))
    path = OUT / "may_root_wdl.jsonl"
    existing = {}
    if path.exists():
        existing = {item["position_id"]: item for item in
                    (json.loads(line) for line in path.read_text().splitlines())}
    with path.open("a") as stream:
        for index, item in enumerate(positions):
            if item["position_id"] in existing:
                continue
            if index:
                time.sleep(DELAY_SECONDS)
            response = query(item["fen"])
            board = chess.Board(item["fen"])
            local = {move.uci() for move in board.legal_moves}
            remote = {move["uci"] for move in response["moves"]}
            if local != remote:
                raise ValueError((item["position_id"], local ^ remote))
            record = {"position_id": item["position_id"], "fen": item["fen"],
                      "response": response}
            stream.write(json.dumps(record, sort_keys=True) + "\n")
            stream.flush()
            existing[item["position_id"]] = record
            if len(existing) % 10 == 0:
                print(f"root WDL {len(existing)}/{len(positions)}", flush=True)
    assert len(existing) == len(positions) == 50
    (OUT / "may_root_wdl_manifest.json").write_text(json.dumps({
        "protocol": "full-game-and-runtime-protocol-v1-secondary-diagnostic",
        "positions_sha256": hashlib.sha256(INPUT.read_bytes()).hexdigest(),
        "games_sha256_before_labels": hashlib.sha256(games_path.read_bytes()).hexdigest(),
        "responses_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "positions": len(positions), "delay_seconds": DELAY_SECONDS,
    }, indent=2) + "\n")


if __name__ == "__main__":
    main()
