"""Compare move-selection compute cost without tablebase calls."""

from __future__ import annotations

import csv
import json
import statistics
import time
from pathlib import Path

import chess

from run_scenario_policies import candidate_metrics, choose, inferred_class, observed_class

ROOT = Path(__file__).parent
POSITIONS = ROOT / "data/endgame_corpus_2025_04/positions.csv"
OUTPUT = ROOT / "results_scenarios_2025_04/benchmark.json"
MODES = ("min_kappa", "neutral", "observed", "inferred")


def select(row: dict, mode: str) -> str:
    board = chess.Board(row["fen"])
    if mode == "min_kappa":
        moves = []
        for move in sorted(board.legal_moves, key=lambda m: m.uci()):
            board.push(move)
            moves.append((board.legal_moves.count(), move.uci()))
            board.pop()
        return min(moves)[1]
    candidates, _ = candidate_metrics(board)
    if mode == "neutral":
        label = "neutral"
    else:
        previous = chess.Board(row["previous_fen"])
        if mode == "observed":
            label, _ = observed_class(previous, board)
        else:
            label, _ = inferred_class(previous, row["last_move_uci"])
    return choose(candidates, label)


def main() -> None:
    with POSITIONS.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 250
    result = {}
    for mode in MODES:
        repetitions = []
        choices = None
        for _ in range(5):
            started = time.perf_counter()
            current = [select(row, mode) for row in rows]
            repetitions.append(time.perf_counter() - started)
            if choices is None:
                choices = current
            assert choices == current
        result[mode] = {
            "seconds_per_250_median": statistics.median(repetitions),
            "seconds_per_250_range": [min(repetitions), max(repetitions)],
            "repetitions": 5,
        }
        print(mode, result[mode], flush=True)
    OUTPUT.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
