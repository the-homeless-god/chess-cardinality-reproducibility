"""Analyze every named position in a pinned Lichess opening catalog snapshot."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import platform
from pathlib import Path

import chess
import chess.pgn

from run_e1 import count_reachability


ROOT = Path(__file__).parent
SOURCE = ROOT / "data" / "openings"
SNAPSHOT = "5a13018164f6bd88f48b3dc31a8e2a39f31a060a"
FIELDS = (
    "eco", "name", "pgn", "epd", "fen", "plies", "turn", "k_local",
    "k_sigma_2", "k_unique_2", "transposition_ratio_2", "nodes", "seconds",
)


def analyze(output: Path, limit: int | None) -> None:
    output.mkdir(parents=True, exist_ok=True)
    for name in ("openings.csv", "manifest.json"):
        if (output / name).exists():
            raise FileExistsError(output / name)
    source_hashes = {
        f"{letter}.tsv": hashlib.sha256((SOURCE / f"{letter}.tsv").read_bytes()).hexdigest()
        for letter in "abcde"
    }
    rows = []
    epds = set()
    for letter in "abcde":
        with (SOURCE / f"{letter}.tsv").open(newline="") as handle:
            for source_row in csv.DictReader(handle, delimiter="\t"):
                game = chess.pgn.read_game(io.StringIO(source_row["pgn"]))
                if game is None or game.errors:
                    raise ValueError((source_row["eco"], source_row["name"], game.errors if game else None))
                board = game.end().board()
                if not board.is_valid():
                    raise ValueError((source_row["eco"], source_row["name"], "invalid position"))
                epd = board.epd()
                if epd in epds:
                    raise ValueError((source_row["eco"], source_row["name"], "duplicate EPD"))
                epds.add(epd)
                result = count_reachability(board, 2, "raw")
                ks, ku = result["k_sigma"], result["k_unique"]
                assert 0 <= ku <= ks
                rows.append({
                    "eco": source_row["eco"], "name": source_row["name"],
                    "pgn": source_row["pgn"], "epd": epd,
                    "fen": board.fen(en_passant="legal"),
                    "plies": len(board.move_stack),
                    "turn": "white" if board.turn else "black",
                    "k_local": board.legal_moves.count(),
                    "k_sigma_2": ks, "k_unique_2": ku,
                    "transposition_ratio_2": round(1 - ku / ks, 12) if ks else None,
                    "nodes": result["nodes"], "seconds": result["seconds"],
                })
                if len(rows) % 100 == 0:
                    print(f"{len(rows)} positions", flush=True)
                if limit is not None and len(rows) >= limit:
                    break
        if limit is not None and len(rows) >= limit:
            break
    with (output / "openings.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    manifest = {
        "protocol": "chess-cardinality-openings-v1",
        "source": "https://github.com/lichess-org/chess-openings",
        "source_commit": SNAPSHOT, "source_sha256": source_hashes,
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "run_e1_sha256": hashlib.sha256((ROOT / "run_e1.py").read_bytes()).hexdigest(),
        "python_version": platform.python_version(), "chess_version": chess.__version__,
        "depth": 2, "mode": "raw", "complete_catalog": limit is None,
        "rows": len(rows), "unique_epd": len(epds),
        "notes": "All named catalog terminal positions; no opening WDL or engine score",
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=ROOT / "results_openings")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    analyze(args.output_dir, args.limit)
