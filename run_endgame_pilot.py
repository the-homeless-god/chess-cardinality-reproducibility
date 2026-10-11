"""Small, preregistered tablebase API check of mobility versus exact outcome.

The fixed fixture positions exercise WDL and fifty-move boundaries.  They are
not a representative statistical sample of all endgames.
"""

from __future__ import annotations

import csv
import hashlib
import json
import platform
import time
import urllib.parse
import urllib.request
from pathlib import Path

import chess


ROOT = Path(__file__).parent
INPUT = ROOT / "data" / "endgame-pilot-positions.csv"
OUTPUT = ROOT / "results_endgame_pilot"
ENDPOINT = "https://tablebase.lichess.ovh/standard"
FIELDS = (
    "position_id", "fen", "pieces", "root_turn", "root_category",
    "move", "move_category_opponent_view", "dtz", "dtm", "kappa_after",
)


def fetch(fen: str) -> dict:
    url = ENDPOINT + "?" + urllib.parse.urlencode({"fen": fen})
    request = urllib.request.Request(url, headers={"User-Agent": "phd-chess-cardinality-research/1.0"})
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)


def main() -> None:
    OUTPUT.mkdir(exist_ok=True)
    for name in ("responses.jsonl", "moves.csv", "manifest.json"):
        if (OUTPUT / name).exists():
            raise FileExistsError(OUTPUT / name)
    with INPUT.open(newline="") as handle:
        fixtures = list(csv.DictReader(handle))
    raw = []
    rows = []
    for index, fixture in enumerate(fixtures):
        if index:
            time.sleep(1)
        board = chess.Board(fixture["fen"])
        assert board.is_valid(), fixture["id"]
        payload = fetch(fixture["fen"])
        assert payload["category"] != "unknown", fixture["id"]
        raw.append({"id": fixture["id"], "fen": fixture["fen"], "response": payload})
        api_moves = {move["uci"]: move for move in payload["moves"]}
        local_moves = {move.uci() for move in board.legal_moves}
        assert set(api_moves) == local_moves, fixture["id"]
        for move_uci in sorted(api_moves):
            move_info = api_moves[move_uci]
            board.push_uci(move_uci)
            rows.append({
                "position_id": fixture["id"], "fen": fixture["fen"],
                "pieces": len(board.piece_map()),
                "root_turn": "white" if not board.turn else "black",
                "root_category": payload["category"], "move": move_uci,
                "move_category_opponent_view": move_info["category"],
                "dtz": move_info["dtz"], "dtm": move_info["dtm"],
                "kappa_after": board.legal_moves.count(),
            })
            board.pop()
        print(f"{fixture['id']}: {payload['category']}, {len(api_moves)} moves", flush=True)
    with (OUTPUT / "responses.jsonl").open("w") as handle:
        for item in raw:
            handle.write(json.dumps(item, sort_keys=True) + "\n")
    with (OUTPUT / "moves.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    manifest = {
        "protocol": "chess-cardinality-endgame-pilot-v1",
        "endpoint": ENDPOINT,
        "input_sha256": hashlib.sha256(INPUT.read_bytes()).hexdigest(),
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "python_version": platform.python_version(), "chess_version": chess.__version__,
        "positions": len(fixtures), "move_rows": len(rows),
        "selection": "fixed edge-case fixtures from lila-tablebase documentation/tests; no representativeness claim",
        "api_category_view": "root category is for side to move; move categories are for opponent after the move",
    }
    (OUTPUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
