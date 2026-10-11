"""Play paired full endgames from a held-out May broadcast sample."""

from __future__ import annotations

import csv
import hashlib
import json
import random
import signal
import statistics
import time
from pathlib import Path

import chess

from run_ga_experiment import choice, counts_2, material, norm_features
from run_scenario_policies import candidate_metrics, choose, inferred_class, observed_class

ROOT = Path(__file__).parent
INPUT = ROOT / "data/endgame_corpus_2025_05_games/positions.csv"
GA_RUNS = ROOT / "results_ga_2025_03/runs.json"
OUT = ROOT / "results_full_game_runtime"
POLICIES = ("observed", "inferred", "neutral", "GA0")
MOVE_LIMIT_SECONDS = 0.250
MAX_PLIES = 200
PIECE_VALUE = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3,
               chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 0}


class MoveTimeout(Exception):
    pass


def alarm_handler(_signum, _frame):
    raise MoveTimeout


def min_kappa(board: chess.Board) -> str:
    values = []
    for move in sorted(board.legal_moves, key=lambda item: item.uci()):
        board.push(move)
        values.append((board.legal_moves.count(), move.uci()))
        board.pop()
    return min(values)[1]


def ga_move(board: chess.Board, weights: list[float]) -> str:
    side = board.turn
    before = material(board, side)
    moves = sorted(move.uci() for move in board.legal_moves)
    features = []
    for uci in moves:
        move = chess.Move.from_uci(uci)
        board.push(move)
        mobility = board.legal_moves.count()
        sigma, unique = counts_2(board)
        features.append((material(board, side) - before, mobility,
                         sigma, unique, int(board.is_check()),
                         int(bool(move.promotion))))
        board.pop()
    row = {"moves": moves, "features": norm_features(features)}
    return moves[choice(row, weights)]


def policy_move(name: str, board: chess.Board, previous: chess.Board,
                last_move_uci: str, weights: list[float]) -> str:
    if name == "min_kappa":
        return min_kappa(board)
    if name == "GA0":
        return ga_move(board, weights)
    if name == "neutral":
        label = "neutral"
    elif name == "observed":
        label = observed_class(previous, board)[0]
    elif name == "inferred":
        label = inferred_class(previous, last_move_uci)[0]
    else:
        raise ValueError(name)
    metrics, _ = candidate_metrics(board)
    return choose(metrics, label)


def make_move(name: str, board: chess.Board, previous: chess.Board,
              last_move_uci: str, weights: list[float]) -> tuple[str, float, bool]:
    started = time.perf_counter()
    timed_out = False
    signal.setitimer(signal.ITIMER_REAL, MOVE_LIMIT_SECONDS)
    try:
        # Search may be interrupted mid push/pop; isolate its mutable board.
        uci = policy_move(name, board.copy(stack=False), previous.copy(stack=False),
                          last_move_uci, weights)
    except MoveTimeout:
        uci = min(move.uci() for move in board.legal_moves)
        timed_out = True
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
    elapsed = time.perf_counter() - started
    assert chess.Move.from_uci(uci) in board.legal_moves
    return uci, elapsed, timed_out


def game(row: dict, candidate: str, candidate_starts: bool,
         weights: list[float]) -> dict:
    board = chess.Board(row["fen"])
    previous = chess.Board(row["previous_fen"])
    last_move_uci = row["last_move_uci"]
    verify = previous.copy()
    verify.push(chess.Move.from_uci(last_move_uci))
    assert verify.fen(en_passant="legal") == board.fen(en_passant="legal")
    candidate_color = board.turn if candidate_starts else not board.turn
    moves, timings = [], []
    cutoff = False
    while True:
        outcome = board.outcome(claim_draw=True)
        if outcome is not None:
            break
        if len(moves) >= MAX_PLIES:
            cutoff = True
            break
        name = candidate if board.turn == candidate_color else "min_kappa"
        uci, elapsed, timed_out = make_move(name, board, previous, last_move_uci, weights)
        timings.append({"policy": name, "seconds": elapsed, "timeout": timed_out})
        previous = board.copy(stack=False)
        board.push(chess.Move.from_uci(uci))
        last_move_uci = uci
        moves.append(uci)
    winner = None if outcome is None else outcome.winner
    score = 0.5 if winner is None else float(winner == candidate_color)
    return {"position_id": row["position_id"], "pieces": int(row["pieces"]),
            "candidate": candidate, "candidate_starts": candidate_starts,
            "candidate_color": "white" if candidate_color else "black",
            "score": score, "winner": None if winner is None else
            ("white" if winner else "black"),
            "termination": "200_ply_cutoff" if cutoff else outcome.termination.name,
            "plies": len(moves), "moves": moves, "timings": timings}


def percentile(values: list[float], p: float) -> float:
    ordered = sorted(values)
    at = (len(ordered) - 1) * p
    lo = int(at)
    hi = min(lo + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (at - lo)


def bootstrap(differences: list[float]) -> list[float]:
    rng = random.Random(20261004)
    values = [statistics.mean(rng.choices(differences, k=len(differences)))
              for _ in range(10000)]
    return [percentile(values, 0.025), percentile(values, 0.975)]


def summarize(records: list[dict]) -> dict:
    by_policy = {}
    pair_scores = {}
    for policy in POLICIES:
        games = [item for item in records if item["candidate"] == policy]
        by_root = {}
        for item in games:
            by_root.setdefault(item["position_id"], []).append(item["score"])
        assert len(games) == 100 and len(by_root) == 50
        assert all(len(values) == 2 for values in by_root.values())
        pair_scores[policy] = {key: sum(values) for key, values in by_root.items()}
        times = [move["seconds"] for item in games for move in item["timings"]
                 if move["policy"] == policy]
        by_policy[policy] = {
            "games": len(games), "wins": sum(item["score"] == 1 for item in games),
            "draws": sum(item["score"] == 0.5 for item in games),
            "losses": sum(item["score"] == 0 for item in games),
            "score_per_100_games": sum(item["score"] for item in games),
            "mean_pair_score_per_root": statistics.mean(pair_scores[policy].values()),
            "paired_advantage_over_identity": bootstrap(
                [value - 1 for value in pair_scores[policy].values()]),
            "technical_draws": sum(item["termination"] == "200_ply_cutoff" for item in games),
            "candidate_moves": len(times),
            "move_seconds_median": statistics.median(times),
            "move_seconds_p95": percentile(times, 0.95),
            "timeouts": sum(move["timeout"] for item in games for move in item["timings"]
                            if move["policy"] == policy),
            "mean_plies": statistics.mean(item["plies"] for item in games),
        }
    root_ids = sorted(pair_scores["observed"])
    comparisons = {}
    for a, b in (("observed", "inferred"), ("observed", "neutral"),
                 ("inferred", "neutral"), ("GA0", "neutral")):
        differences = [pair_scores[a][key] - pair_scores[b][key] for key in root_ids]
        comparisons[f"{a}-{b}"] = {"mean_pair_difference": statistics.mean(differences),
                                     "ci95": bootstrap(differences)}
    return {"protocol": "full-game-and-runtime-protocol-v1",
            "positions_sha256": hashlib.sha256(INPUT.read_bytes()).hexdigest(),
            "ga_runs_sha256": hashlib.sha256(GA_RUNS.read_bytes()).hexdigest(),
            "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "games_total": len(records), "max_plies": MAX_PLIES,
            "move_limit_seconds": MOVE_LIMIT_SECONDS,
            "policies": by_policy, "comparisons": comparisons}


def main() -> None:
    OUT.mkdir(exist_ok=True)
    path = OUT / "games.jsonl"
    if path.exists():
        raise FileExistsError(path)
    with INPUT.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 50
    runs = json.loads(GA_RUNS.read_text())
    weights = next(item["weights"] for item in runs
                   if item["mode"] == "GA0+GA1+GA2" and item["seed"] == 100)
    signal.signal(signal.SIGALRM, alarm_handler)
    records = []
    with path.open("w") as stream:
        for index, row in enumerate(rows, 1):
            for candidate in POLICIES:
                for starts in (True, False):
                    item = game(row, candidate, starts, weights)
                    records.append(item)
                    stream.write(json.dumps(item, ensure_ascii=False) + "\n")
                    stream.flush()
            if index % 5 == 0:
                print(f"roots {index}/50; games {len(records)}/400", flush=True)
    summary = summarize(records)
    summary["games_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    (OUT / "games_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print("scores", {name: stats["score_per_100_games"]
                     for name, stats in summary["policies"].items()}, flush=True)


if __name__ == "__main__":
    main()
