"""Frozen chess-policy experiment; tablebase labels never enter move features."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import random
import statistics
import time
from pathlib import Path

import chess

ROOT = Path(__file__).parent
POSITIONS = ROOT / "data/endgame_corpus_2025_03/positions.csv"
RESPONSES = ROOT / "results_endgame_2025_03/responses.jsonl"
OUT = ROOT / "results_ga_2025_03"
SEEDS = range(100, 110)
CONFIGS = ((0.15, 0.5), (0.4, 0.7), (0.8, 0.9))
PIECE_VALUE = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3,
               chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 0}
CAT_SCORE = {"win": 2, "cursed-win": 1, "draw": 1,
             "blessed-loss": 1, "loss": 0}


def material(board: chess.Board, color: bool) -> int:
    return sum(PIECE_VALUE[t] * (len(board.pieces(t, color)) -
                                 len(board.pieces(t, not color)))
               for t in PIECE_VALUE)


def counts_2(board: chess.Board) -> tuple[int, int]:
    total = 0
    unique = set()
    for reply in list(board.legal_moves):
        board.push(reply)
        for continuation in list(board.legal_moves):
            board.push(continuation)
            total += 1
            unique.add(board.fen(en_passant="legal"))
            board.pop()
        board.pop()
    return total, len(unique)


def norm_features(rows: list[tuple[float, ...]]) -> list[list[float]]:
    columns = list(zip(*rows))
    bounds = [(min(col), max(col)) for col in columns]
    return [[0.0 if hi == lo else (2 * value - hi - lo) / (hi - lo)
             for value, (lo, hi) in zip(row, bounds)] for row in rows]


def prepare() -> list[dict]:
    with POSITIONS.open(newline="") as stream:
        positions = list(csv.DictReader(stream))
    labels = {r["position_id"]: r["response"] for r in
              (json.loads(line) for line in RESPONSES.read_text().splitlines())}
    assert len(positions) == len(labels) == 250
    result = []
    for index, position in enumerate(positions):
        board = chess.Board(position["fen"])
        color = board.turn
        start_material = material(board, color)
        response = labels[position["position_id"]]
        by_move = {m["uci"]: m for m in response["moves"]}
        moves = sorted(m.uci() for m in board.legal_moves)
        features = []
        scores = []
        categories = []
        for uci in moves:
            move = chess.Move.from_uci(uci)
            board.push(move)
            mobility = board.legal_moves.count()
            sigma, unique = counts_2(board)
            features.append((material(board, color) - start_material,
                             mobility, sigma, unique,
                             int(board.is_check()), int(bool(move.promotion))))
            category = by_move[uci]["category"]
            categories.append(category)
            scores.append(2 - CAT_SCORE[category])
            board.pop()
        assert len(moves) == len(by_move)
        piece_index = index % 50
        split = "train" if piece_index < 30 else "val" if piece_index < 40 else "test"
        result.append({"id": position["position_id"], "pieces": int(position["pieces"]),
                       "fen": position["fen"], "split": split, "moves": moves,
                       "features": norm_features(features), "raw": features,
                       "scores": scores, "categories": categories,
                       "root_category": response["category"],
                       "best": max(scores), "informative": len(set(scores)) > 1})
        if (index + 1) % 25 == 0:
            print(f"features {index + 1}/250", flush=True)
    return result


def choice(row: dict, weights: list[float]) -> int:
    return max(range(len(row["moves"])),
               key=lambda j: (sum(a * b for a, b in zip(weights, row["features"][j])),
                              -j))


def accuracy(data: list[dict], weights: list[float]) -> float:
    return statistics.mean(row["scores"][choice(row, weights)] == row["best"]
                           for row in data)


def fitness(data: list[dict], weights: list[float]) -> float:
    return statistics.mean(1 - (row["best"] - row["scores"][choice(row, weights)]) / 2
                           for row in data)


class GA:
    def __init__(self, seed: int, config: tuple[float, float], train: list[dict], val: list[dict]):
        self.rng = random.Random(seed)
        self.config = config
        self.train = train
        self.val = val
        self.population = [[self.rng.uniform(-2, 2) for _ in range(6)] for _ in range(12)]
        self.evaluations = 0
        self.val_evaluations = 0
        self.best_weights = None
        self.best_val = -1.0
        self.best_train = -1.0
        self.trace = []

    def generation(self) -> None:
        scored = [(fitness(self.train, w), w) for w in self.population]
        self.evaluations += len(scored)
        scored.sort(key=lambda item: item[0], reverse=True)
        candidate = scored[0][1]
        val_score = accuracy(self.val, candidate)
        self.val_evaluations += 1
        if val_score > self.best_val or (val_score == self.best_val and scored[0][0] > self.best_train):
            self.best_val = val_score
            self.best_train = scored[0][0]
            self.best_weights = candidate.copy()
        self.trace.append({"evaluations": self.evaluations,
                           "train_fitness": scored[0][0], "val_accuracy": val_score,
                           "best_val_accuracy": self.best_val})
        def tournament():
            return max(self.rng.sample(scored, 3), key=lambda pair: pair[0])[1]
        new = [scored[0][1].copy(), scored[1][1].copy()]
        while len(new) < 12:
            a, b = tournament(), tournament()
            if self.rng.random() < self.config[1]:
                mix = self.rng.random()
                child = [mix * x + (1 - mix) * y for x, y in zip(a, b)]
            else:
                child = a.copy()
            child = [max(-2, min(2, x + self.rng.gauss(0, self.config[0])))
                     if self.rng.random() < 0.5 else x for x in child]
            new.append(child)
        self.population = new


def run_mode(mode: str, seed: int, train: list[dict], val: list[dict]) -> dict:
    started = time.perf_counter()
    if mode == "GA2":
        ga = GA(seed, CONFIGS[1], train, val)
        for _ in range(50):
            ga.generation()
        chosen = ga
        used = 600
        val_used = ga.val_evaluations
        traces = [ga.trace]
        selected_config = 1
    else:
        candidates = [GA(seed * 10 + i, config, train, val) for i, config in enumerate(CONFIGS)]
        for ga in candidates:
            for _ in range(10):
                ga.generation()
        selected_config = max(range(3), key=lambda i: (candidates[i].best_val,
                                                        candidates[i].best_train, -i))
        chosen = candidates[selected_config]
        used = 360
        plateau = 0
        old_best = chosen.best_val
        while used < 600:
            chosen.generation()
            used += 12
            if chosen.best_val > old_best:
                plateau = 0
                old_best = chosen.best_val
            else:
                plateau += 1
            if mode == "GA0+GA1+GA2" and chosen.best_val >= 0.90 and plateau >= 3:
                break
        val_used = sum(g.val_evaluations for g in candidates)
        traces = [g.trace for g in candidates]
    return {"mode": mode, "seed": seed, "weights": chosen.best_weights,
            "selected_config": selected_config, "train_fitness": chosen.best_train,
            "val_accuracy": chosen.best_val, "fitness_evaluations": used,
            "validation_evaluations": val_used, "seconds": time.perf_counter() - started,
            "stop": "threshold_plateau" if used < 600 else "budget", "traces": traces}


def baseline_index(row: dict, name: str, rng: random.Random) -> int:
    if name == "random":
        return rng.randrange(len(row["moves"]))
    column, descending = {"max_kappa": (1, True), "min_kappa": (1, False),
                          "max_ku2": (3, True), "material": (0, True)}[name]
    return max(range(len(row["moves"])),
               key=lambda j: ((1 if descending else -1) * row["raw"][j][column], -j))


def main() -> None:
    OUT.mkdir(exist_ok=True)
    started = time.perf_counter()
    data = prepare()
    feature_seconds = time.perf_counter() - started
    (OUT / "features.json").write_text(json.dumps(data, ensure_ascii=False) + "\n")
    train = [r for r in data if r["split"] == "train"]
    val = [r for r in data if r["split"] == "val"]
    test = [r for r in data if r["split"] == "test"]
    results = []
    for seed in SEEDS:
        for mode in ("GA2", "GA1+GA2", "GA0+GA1+GA2"):
            result = run_mode(mode, seed, train, val)
            result["test_choices"] = {r["id"]: choice(r, result["weights"]) for r in test}
            results.append(result)
            print(seed, mode, result["val_accuracy"], result["fitness_evaluations"], flush=True)
        rng = random.Random(seed)
        for mode in ("random", "max_kappa", "min_kappa", "max_ku2", "material"):
            results.append({"mode": mode, "seed": seed,
                            "fitness_evaluations": 0, "validation_evaluations": 0,
                            "test_choices": {r["id"]: baseline_index(r, mode, rng) for r in test}})
    (OUT / "runs.json").write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n")
    (OUT / "manifest.json").write_text(json.dumps({
        "protocol": "ga-experiment-protocol-v1", "position_sha256": hashlib.sha256(POSITIONS.read_bytes()).hexdigest(),
        "response_sha256": hashlib.sha256(RESPONSES.read_bytes()).hexdigest(),
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "seeds": list(SEEDS), "split": {"train": len(train), "val": len(val), "test": len(test)},
        "feature_seconds": feature_seconds,
        "total_seconds": time.perf_counter() - started, "runs": len(results)
    }, indent=2) + "\n")


if __name__ == "__main__":
    main()
