"""Select the May 2025 full-game starts without outcomes or tablebase labels."""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path

import chess
import chess.pgn

ROOT = Path(__file__).parent
OUT = ROOT / "data/endgame_corpus_2025_05_games"
SOURCE = "https://database.lichess.org/broadcast/lichess_db_broadcast_2025-05.pgn.zst"
SOURCE_SHA256 = "ed1b62de4c4f81e19d8e269a0ddbb4c5133361ff942439938f9d20f3d904795c"
SEED = "20261004-may-full-games"
FIELDS = ("position_id", "game_url", "game_date", "ply", "pieces", "fen",
          "previous_fen", "last_move_uci", "selection_hash")


def main() -> None:
    if OUT.exists():
        raise FileExistsError(OUT)
    excluded_fens = set()
    for month in ("03", "04"):
        filename = ROOT / f"data/endgame_corpus_2025_{month}/positions.csv"
        with filename.open(newline="") as stream:
            excluded_fens.update(row["fen"] for row in csv.DictReader(stream))
    candidates = []
    counts = {"games": 0, "standard": 0, "with_candidate": 0, "invalid_pgn": 0}
    while game := chess.pgn.read_game(sys.stdin):
        counts["games"] += 1
        if game.headers.get("Variant", "Standard") != "Standard":
            continue
        counts["standard"] += 1
        if game.errors:
            counts["invalid_pgn"] += 1
            continue
        board = game.board()
        found = set()
        game_url = game.headers.get("GameURL") or f"index:{counts['games']}"
        for ply, move in enumerate(game.mainline_moves(), 1):
            previous_fen = board.fen(en_passant="legal")
            board.push(move)
            pieces = len(board.piece_map())
            if pieces not in range(3, 8) or pieces in found or ply < 20:
                continue
            fen = board.fen(en_passant="legal")
            if (fen in excluded_fens or board.castling_rights or not board.is_valid()
                    or board.legal_moves.count() < 2):
                continue
            found.add(pieces)
            key = f"{SEED}|{game_url}|{ply}|{fen}"
            candidates.append({
                "game_url": game_url, "game_date": game.headers.get("Date", ""),
                "ply": ply, "pieces": pieces, "fen": fen,
                "previous_fen": previous_fen, "last_move_uci": move.uci(),
                "selection_hash": hashlib.sha256(key.encode()).hexdigest(),
            })
        if found:
            counts["with_candidate"] += 1
        if counts["games"] % 5000 == 0:
            print(f"read {counts['games']} games", file=sys.stderr, flush=True)
    selected = []
    games, fens = set(), set()
    for pieces in range(3, 8):
        ranked = sorted((x for x in candidates if x["pieces"] == pieces),
                        key=lambda x: x["selection_hash"])
        take = 0
        for item in ranked:
            if item["game_url"] in games or item["fen"] in fens:
                continue
            selected.append(item)
            games.add(item["game_url"])
            fens.add(item["fen"])
            take += 1
            if take == 10:
                break
        if take != 10:
            raise ValueError(f"Only {take} unique {pieces}-piece positions")
    for index, item in enumerate(selected, 1):
        item["position_id"] = f"B202505-{index:03d}"
    OUT.mkdir(parents=True)
    path = OUT / "positions.csv"
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, FIELDS)
        writer.writeheader()
        writer.writerows(selected)
    manifest = {
        "protocol": "full-game-and-runtime-protocol-v1",
        "source_url": SOURCE, "source_sha256": SOURCE_SHA256,
        "source_license": "CC BY-SA 4.0", "seed": SEED,
        "selection": "first valid 3-7-piece position per game and stratum after ply 20; SHA-256 rank, 10 per stratum, at most one per game, excluding March and April FEN; no outcomes read",
        "source_counts": counts, "candidate_counts": {
            str(k): sum(x["pieces"] == k for x in candidates) for k in range(3, 8)
        },
        "rows": len(selected),
        "positions_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    (OUT / "selection_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    (OUT / "SOURCE.md").write_text(
        "# Lichess Broadcast May 2025: корпус полных партий\n\n"
        f"Источник: [официальный архив Lichess]({SOURCE}), лицензия CC BY-SA 4.0.\n"
        f"SHA-256 архива: `{SOURCE_SHA256}`.\n"
        "В `positions.csv` сохранены FEN, контекст предыдущего хода и URL партий. "
        "Архив PGN хранится только во временной папке. "
        "Правило отбора и хеш корпуса находятся в `selection_manifest.json`.\n"
    )
    print(json.dumps(manifest["candidate_counts"]), file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
