"""Probe a frozen broadcast-position sample through the public Syzygy API.

One request is made at a time.  Responses are append-only for safe resume.
The API labels are not used to select positions.
"""

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
INPUT = ROOT / "data" / "endgame_corpus_2025_03" / "positions.csv"
OUTPUT = ROOT / "results_endgame_2025_03"
ENDPOINT = "https://tablebase.lichess.ovh/standard"
DELAY_SECONDS = 1.2


def query(fen: str) -> dict:
    url = ENDPOINT + "?" + urllib.parse.urlencode({"fen": fen})
    request = urllib.request.Request(url, headers={"User-Agent": "phd-chess-cardinality-research/1.0"})
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
    OUTPUT.mkdir(exist_ok=True)
    with INPUT.open(newline="") as handle:
        positions = list(csv.DictReader(handle))
    existing = {}
    path = OUTPUT / "responses.jsonl"
    if path.exists():
        for line in path.read_text().splitlines():
            item = json.loads(line)
            existing[item["position_id"]] = item
    with path.open("a") as handle:
        for index, item in enumerate(positions):
            if item["position_id"] in existing:
                continue
            if index:
                time.sleep(DELAY_SECONDS)
            board = chess.Board(item["fen"])
            assert board.is_valid() and len(board.piece_map()) == int(item["pieces"])
            response = query(item["fen"])
            if response["category"] == "unknown":
                raise ValueError((item["position_id"], "unknown tablebase result"))
            local = {move.uci() for move in board.legal_moves}
            remote = {move["uci"] for move in response["moves"]}
            if local != remote:
                raise ValueError((item["position_id"], local ^ remote))
            record = {
                "position_id": item["position_id"],
                "fen": item["fen"],
                "response": response,
            }
            handle.write(json.dumps(record, sort_keys=True) + "\n")
            handle.flush()
            existing[item["position_id"]] = record
            if len(existing) % 10 == 0:
                print(f"{len(existing)}/{len(positions)} tablebase positions", flush=True)
    if len(existing) != len(positions):
        raise ValueError(f"Incomplete: {len(existing)}/{len(positions)}")
    manifest = {
        "protocol": "chess-endgame-broadcast-tablebase-v1",
        "endpoint": ENDPOINT,
        "positions_sha256": hashlib.sha256(INPUT.read_bytes()).hexdigest(),
        "responses_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "positions": len(positions),
        "delay_seconds": DELAY_SECONDS,
        "move_category_view": "side to move after the candidate move",
    }
    (OUTPUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
