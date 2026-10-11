"""Freeze both A/B/C policy predictions before any April tablebase probes."""

from __future__ import annotations

import csv
import hashlib
import json
import time
from pathlib import Path

import chess

ROOT = Path(__file__).parent
INPUT = ROOT / "data/endgame_corpus_2025_04/positions.csv"
OUTPUT = ROOT / "results_scenarios_2025_04"


def potential(board: chess.Board, color: chess.Color) -> int:
    probe = board.copy()
    if probe.turn != color:
        probe.turn = color
        probe.ep_square = None
    return probe.legal_moves.count()


def observed_class(previous: chess.Board, current: chess.Board) -> tuple[str, dict]:
    player = current.turn
    before_player = potential(previous, player)
    after_player = current.legal_moves.count()
    before_opponent = previous.legal_moves.count()
    after_opponent = potential(current, not player)
    a = (before_player - after_player) / max(1, before_player)
    b = (after_opponent - before_opponent) / max(1, before_opponent)
    if a > 0 and a > b:
        label = "A"
    elif b > 0 and b > a:
        label = "B"
    else:
        label = "neutral"
    return label, {
        "before_player": before_player, "after_player": after_player,
        "before_opponent": before_opponent, "after_opponent": after_opponent,
        "relative_A_effect": a, "relative_B_effect": b,
    }


def percentile(values: list[int], actual: int) -> float:
    if len(values) == 1:
        return 0.5
    return (sum(x < actual for x in values) +
            0.5 * sum(x == actual for x in values)) / len(values)


def inferred_class(previous: chess.Board, actual_uci: str) -> tuple[str, dict]:
    opponent = previous.turn
    candidates = []
    for move in sorted(previous.legal_moves, key=lambda m: m.uci()):
        previous.push(move)
        candidates.append({
            "uci": move.uci(),
            "A_score": -previous.legal_moves.count(),
            "B_score": potential(previous, opponent),
        })
        previous.pop()
    actual = next(x for x in candidates if x["uci"] == actual_uci)
    pa = percentile([x["A_score"] for x in candidates], actual["A_score"])
    pb = percentile([x["B_score"] for x in candidates], actual["B_score"])
    label = "A" if pa > pb else "B" if pb > pa else "neutral"
    return label, {
        "alternatives": len(candidates), "A_percentile": pa, "B_percentile": pb,
        "actual_A_score": actual["A_score"], "actual_B_score": actual["B_score"],
    }


def candidate_metrics(board: chess.Board) -> tuple[list[dict], dict]:
    own = board.legal_moves.count()
    opp_potential = potential(board, not board.turn)
    gap_before = abs(own - opp_potential)
    metrics = []
    replies_seen = 0
    for move in sorted(board.legal_moves, key=lambda m: m.uci()):
        board.push(move)
        immediate_mate = board.is_checkmate()
        opponent_moves = board.legal_moves.count()
        future_own = []
        gaps = []
        opponent_mate_in_one = False
        for reply in list(board.legal_moves):
            board.push(reply)
            count = board.legal_moves.count()
            future_own.append(count)
            gaps.append(abs(opponent_moves - count))
            opponent_mate_in_one |= board.is_checkmate()
            board.pop()
            replies_seen += 1
        minimum_own = min(future_own, default=0)
        worst_gap = max(gaps, default=opponent_moves)
        a = opp_potential - opponent_moves
        b = minimum_own - own
        c = gap_before - worst_gap
        metrics.append({
            "uci": move.uci(), "mate_now": immediate_mate,
            "opponent_mate_in_one": opponent_mate_in_one,
            "opponent_moves": opponent_moves,
            "worst_own_moves_after_reply": minimum_own,
            "worst_mobility_gap": worst_gap,
            "A_improvement": a, "B_improvement": b, "C_improvement": c,
        })
        board.pop()
    return metrics, {"own_before": own, "opponent_potential_before": opp_potential,
                     "mobility_gap_before": gap_before, "replies_analyzed": replies_seen}


def choose(metrics: list[dict], opponent_class: str) -> str:
    immediate = [item for item in metrics if item["mate_now"]]
    if immediate:
        return immediate[0]["uci"]
    safe = [item for item in metrics if not item["opponent_mate_in_one"]]
    pool = safe or metrics
    order = ("B", "C", "A") if opponent_class == "A" else ("A", "B", "C")
    def key(item):
        score = []
        for letter in order:
            value = item[f"{letter}_improvement"]
            score.extend((int(value > 0), max(0, value)))
        score.extend((-item["opponent_moves"], item["worst_own_moves_after_reply"],
                      -item["worst_mobility_gap"]))
        return tuple(score)
    return max(pool, key=key)["uci"]


def main() -> None:
    OUTPUT.mkdir(exist_ok=True)
    with INPUT.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 250
    predictions = []
    for index, row in enumerate(rows, 1):
        start = time.perf_counter()
        previous = chess.Board(row["previous_fen"])
        current = chess.Board(row["fen"])
        last = chess.Move.from_uci(row["last_move_uci"])
        assert last in previous.legal_moves
        check = previous.copy()
        check.push(last)
        assert check.fen(en_passant="legal") == current.fen(en_passant="legal")
        observed, observed_details = observed_class(previous, current)
        inferred, inferred_details = inferred_class(previous, last.uci())
        choices, context = candidate_metrics(current)
        predictions.append({
            "position_id": row["position_id"], "fen": row["fen"],
            "last_move_uci": last.uci(),
            "observed_class": observed, "observed_details": observed_details,
            "inferred_class": inferred, "inferred_details": inferred_details,
            "context": context, "candidates": choices,
            "choices": {
                "observed": choose(choices, observed),
                "inferred": choose(choices, inferred),
                "neutral": choose(choices, "neutral"),
                "min_kappa": min(choices, key=lambda x: (x["opponent_moves"], x["uci"]))["uci"],
            },
            "seconds": time.perf_counter() - start,
        })
        if index % 25 == 0:
            print(f"predictions {index}/250", flush=True)
    path = OUTPUT / "predictions.json"
    if path.exists():
        raise FileExistsError(path)
    path.write_text(json.dumps(predictions, ensure_ascii=False, indent=2) + "\n")
    manifest = {
        "protocol": "scenario-comparison-protocol-v1",
        "positions_sha256": hashlib.sha256(INPUT.read_bytes()).hexdigest(),
        "predictions_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "positions": len(predictions),
        "labels_used": False,
    }
    (OUTPUT / "prediction_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    )


if __name__ == "__main__":
    main()
