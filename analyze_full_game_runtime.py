"""Audit May match logs and report discrete paired evidence and latency."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import statistics
from collections import Counter
from pathlib import Path

import chess

ROOT = Path(__file__).parent
OUT = ROOT / "results_full_game_runtime"
POSITIONS = ROOT / "data/endgame_corpus_2025_05_games/positions.csv"
POLICIES = ("observed", "inferred", "neutral", "GA0")


def percentile(values: list[float], p: float) -> float:
    ordered = sorted(values)
    at = (len(ordered) - 1) * p
    lo = int(at)
    hi = min(lo + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (at - lo)


def sign_test(positives: int, negatives: int) -> float:
    n = positives + negatives
    if not n:
        return 1.0
    return min(1.0, 2 * sum(math.comb(n, k) for k in range(min(positives, negatives) + 1)) / 2**n)


def main() -> None:
    games_path = OUT / "games.jsonl"
    roots_path = OUT / "may_root_wdl.jsonl"
    games = [json.loads(line) for line in games_path.read_text().splitlines()]
    roots = {item["position_id"]: item for item in
             (json.loads(line) for line in roots_path.read_text().splitlines())}
    with POSITIONS.open(newline="") as stream:
        positions = list(csv.DictReader(stream))
    assert len(games) == 400 and len(roots) == len(positions) == 50
    for item in games:
        board = chess.Board(next(row["fen"] for row in positions
                                 if row["position_id"] == item["position_id"]))
        for uci in item["moves"]:
            move = chess.Move.from_uci(uci)
            assert move in board.legal_moves
            board.push(move)
        assert len(item["moves"]) == len(item["timings"]) == item["plies"]
        assert abs(item["score"] - (0.5 if item["winner"] is None else
                                   float((item["winner"] == "white") ==
                                         (item["candidate_color"] == "white")))) < 1e-12
    pair_scores = {}
    paired_evidence = {}
    for policy in POLICIES:
        pair_scores[policy] = {}
        for item in games:
            if item["candidate"] == policy:
                pair_scores[policy][item["position_id"]] = (
                    pair_scores[policy].get(item["position_id"], 0) + item["score"])
        assert len(pair_scores[policy]) == 50
        changes = [value - 1 for value in pair_scores[policy].values()]
        positives = sum(x > 0 for x in changes)
        negatives = sum(x < 0 for x in changes)
        paired_evidence[policy] = {
            "roots_better_than_identity": positives,
            "roots_worse_than_identity": negatives,
            "roots_tied": sum(x == 0 for x in changes),
            "two_sided_exact_sign_p": sign_test(positives, negatives),
        }
    differences = {}
    for a, b in (("observed", "inferred"), ("observed", "neutral"),
                 ("inferred", "neutral"), ("GA0", "neutral")):
        changes = [pair_scores[a][key] - pair_scores[b][key] for key in pair_scores[a]]
        pos, neg = sum(x > 0 for x in changes), sum(x < 0 for x in changes)
        differences[f"{a}-{b}"] = {"positive_roots": pos, "negative_roots": neg,
                                     "tied_roots": sum(x == 0 for x in changes),
                                     "two_sided_exact_sign_p": sign_test(pos, neg)}
    labels = Counter(item["response"]["category"] for item in roots.values())
    informative = sum(len({move["category"] for move in item["response"]["moves"]}) > 1
                      for item in roots.values())
    times = {}
    for name in (*POLICIES, "min_kappa"):
        values = [move["seconds"] for item in games for move in item["timings"]
                  if move["policy"] == name]
        times[name] = {"moves": len(values), "median_seconds": statistics.median(values),
                       "p95_seconds": percentile(values, 0.95)}
    diagnostic = {
        "protocol": "full-game-and-runtime-protocol-v1-secondary-diagnostics",
        "positions_sha256": hashlib.sha256(POSITIONS.read_bytes()).hexdigest(),
        "games_sha256": hashlib.sha256(games_path.read_bytes()).hexdigest(),
        "root_wdl_sha256": hashlib.sha256(roots_path.read_bytes()).hexdigest(),
        "root_categories": dict(labels), "informative_roots": informative,
        "initially_terminal_roots": sum(chess.Board(row["fen"]).outcome(claim_draw=True)
                                        is not None for row in positions),
        "termination_counts": dict(Counter(item["termination"] for item in games)),
        "paired_sign_tests": paired_evidence, "policy_pair_sign_tests": differences,
        "move_latencies": times,
    }
    (OUT / "diagnostics.json").write_text(json.dumps(diagnostic, indent=2) + "\n")
    print(json.dumps(diagnostic, indent=2))


if __name__ == "__main__":
    main()
