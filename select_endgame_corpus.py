"""Preselect endgame positions from an official Lichess broadcast PGN snapshot.

Selection never reads game outcomes or tablebase responses.  One position per
game is kept in the final corpus, stratified by number of pieces.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

import chess
import chess.pgn


SOURCE_URL = "https://database.lichess.org/broadcast/lichess_db_broadcast_2025-03.pgn.zst"
SOURCE_SHA256 = "840bdb7d640f82032f8373c86efcb69d0801c0d54cf3edf2152e4b8d25b8da87"
SEED = "20261004"
TARGET_PER_PIECE_COUNT = 50
FIELDS = ("position_id", "game_url", "game_date", "ply", "pieces", "fen", "selection_hash")


def collect(stream) -> tuple[list[dict], dict]:
    candidates: list[dict] = []
    counts = {"games": 0, "standard": 0, "invalid_pgn": 0, "with_candidate": 0}
    while game := chess.pgn.read_game(stream):
        counts["games"] += 1
        if game.headers.get("Variant", "Standard") != "Standard":
            continue
        counts["standard"] += 1
        if game.errors:
            counts["invalid_pgn"] += 1
            continue
        board = game.board()
        found = {}
        for ply, move in enumerate(game.mainline_moves(), 1):
            board.push(move)
            pieces = len(board.piece_map())
            if not 3 <= pieces <= 7 or pieces in found or ply < 20:
                continue
            if board.castling_rights or not board.is_valid() or board.legal_moves.count() < 2:
                continue
            found[pieces] = {"ply": ply, "fen": board.fen(en_passant="legal")}
        if not found:
            continue
        counts["with_candidate"] += 1
        game_url = game.headers.get("GameURL") or f"index:{counts['games']}"
        for pieces, record in found.items():
            payload = {
                "game_url": game_url,
                "game_date": game.headers.get("Date", ""),
                "ply": record["ply"], "pieces": pieces, "fen": record["fen"],
            }
            label = f"{SEED}|{game_url}|{record['ply']}|{record['fen']}"
            payload["selection_hash"] = hashlib.sha256(label.encode()).hexdigest()
            candidates.append(payload)
        if counts["games"] % 2000 == 0:
            print(f"read {counts['games']} games", file=sys.stderr, flush=True)
    return candidates, counts


def select(candidates: list[dict]) -> list[dict]:
    selected = []
    used_games = set()
    used_positions = set()
    for pieces in range(3, 8):
        stratum = sorted((item for item in candidates if item["pieces"] == pieces), key=lambda x: x["selection_hash"])
        taken = 0
        for item in stratum:
            if item["game_url"] in used_games or item["fen"] in used_positions:
                continue
            selected.append(item)
            used_games.add(item["game_url"])
            used_positions.add(item["fen"])
            taken += 1
            if taken == TARGET_PER_PIECE_COUNT:
                break
        if taken < TARGET_PER_PIECE_COUNT:
            raise ValueError(f"Only {taken} unique positions available for {pieces} pieces")
    for index, item in enumerate(selected, 1):
        item["position_id"] = f"B202503-{index:03d}"
    return selected


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).parent / "data" / "endgame_corpus_2025_03")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name in ("positions.csv", "selection_manifest.json"):
        if (args.output_dir / name).exists():
            raise FileExistsError(args.output_dir / name)
    candidates, counts = collect(sys.stdin)
    selected = select(candidates)
    with (args.output_dir / "positions.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, FIELDS)
        writer.writeheader()
        writer.writerows(selected)
    manifest = {
        "protocol": "chess-endgame-broadcast-selection-v1",
        "source_url": SOURCE_URL, "source_sha256": SOURCE_SHA256,
        "source_license": "CC BY-SA 4.0",
        "seed": SEED, "target_per_piece_count": TARGET_PER_PIECE_COUNT,
        "filters": "standard games, first reachable position per 3-7 piece count after ply 20, no castling, valid board, >=2 legal moves",
        "selection": "SHA-256 rank within piece count; one position per game and FEN across final sample; no game result or tablebase data used",
        "source_counts": counts,
        "candidate_counts": {str(k): sum(x["pieces"] == k for x in candidates) for k in range(3, 8)},
        "selected_counts": {str(k): sum(x["pieces"] == k for x in selected) for k in range(3, 8)},
        "rows": len(selected),
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    (args.output_dir / "selection_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"candidate_counts": manifest["candidate_counts"], "selected_counts": manifest["selected_counts"]}), file=sys.stderr)


if __name__ == "__main__":
    main()
