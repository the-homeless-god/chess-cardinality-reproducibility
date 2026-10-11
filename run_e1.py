"""Frozen E0/E1 chess cardinality experiment (protocol v1).

Depth is counted from the position *after* a candidate first move.  The
canonical key conservatively includes the repetition history since the last
irreversible move; this can distinguish more positions than strictly needed,
but never merges states with different draw rights.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import time
from collections import Counter
from pathlib import Path

import chess


PROTOCOL = "chess-cardinality-e1-v1"
START_FEN = chess.STARTING_FEN
DEPTHS = (1, 2, 3, 4)
PERFT = {1: 20, 2: 400, 3: 8902, 4: 197281}
EXTRA_PERFT = (
    ("kiwipete", "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1", {1: 48, 2: 2039, 3: 97862}),
    ("position_3", "8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1", {1: 14, 2: 191, 3: 2812}),
)
FIELDS = (
    "protocol", "fen", "side", "move", "depth", "mode", "k_local",
    "k_sigma", "k_unique", "transposition_ratio", "delta", "rho",
    "min_reply_k_sigma", "max_reply_k_sigma", "nodes", "seconds",
    "terminal_count", "k_viable", "complete", "derived_from", "seed",
)


def position_base(board: chess.Board) -> tuple[str, bool, str, int | None]:
    """Public-rule fields affecting legal moves and repetition equality."""
    ep = board.ep_square if board.has_legal_en_passant() else None
    return board.board_fen(), board.turn, board.castling_xfen(), ep


def repetition_history(board: chess.Board) -> Counter:
    """Keep positions since the last irreversible move, with counts capped at 2."""
    replay = board.root()
    history: Counter = Counter({position_base(replay): 1})
    for move in board.move_stack:
        irreversible = replay.is_irreversible(move)
        replay.push(move)
        if irreversible:
            history.clear()
        key = position_base(replay)
        history[key] = min(2, history[key] + 1)
    return history


def canonical_key(board: chess.Board, history: Counter) -> tuple:
    return position_base(board), board.halfmove_clock, frozenset(history.items())


def perft(board: chess.Board, depth: int) -> int:
    if depth == 0:
        return 1
    total = 0
    for move in board.legal_moves:
        board.push(move)
        total += perft(board, depth - 1)
        board.pop()
    return total


def count_reachability(board: chess.Board, depth: int, mode: str) -> dict:
    """Count exactly-depth legal paths and unique canonical endpoints."""
    history = repetition_history(board)
    seen = {canonical_key(board, history)}
    unique: set[tuple] = set()
    reply_counts: Counter = Counter()
    nodes = 0
    terminal = 0

    def walk(remaining: int, path: frozenset, hist: Counter, reply: str | None, key: tuple) -> int:
        nonlocal nodes, terminal
        if remaining == 0:
            unique.add(key)
            if reply is not None:
                reply_counts[reply] += 1
            return 1
        if board.is_game_over(claim_draw=False):
            terminal += 1
            return 0
        total = 0
        for move in board.legal_moves:
            irreversible = board.is_irreversible(move)
            move_uci = move.uci() if reply is None else reply
            board.push(move)
            nodes += 1
            next_hist = Counter() if irreversible else hist.copy()
            base = position_base(board)
            next_hist[base] = min(2, next_hist[base] + 1)
            key = canonical_key(board, next_hist)
            if mode == "simple" and key in path:
                board.pop()
                continue
            next_path = path | {key} if mode == "simple" else path
            total += walk(remaining - 1, next_path, next_hist, move_uci, key)
            board.pop()
        return total

    t0 = time.perf_counter()
    k_sigma = walk(depth, frozenset(seen), history, None, next(iter(seen)))
    seconds = time.perf_counter() - t0
    return {
        "k_sigma": k_sigma,
        "k_unique": len(unique),
        "nodes": nodes,
        "seconds": round(seconds, 6),
        "terminal": terminal,
        "min_reply_k_sigma": min(reply_counts.values()) if reply_counts else None,
        "max_reply_k_sigma": max(reply_counts.values()) if reply_counts else None,
    }


def run_e0() -> dict:
    board = chess.Board(START_FEN)
    observed = {str(depth): perft(board, depth) for depth in PERFT}
    assert observed == {str(k): v for k, v in PERFT.items()}
    assert board.fen() == START_FEN
    extra_observed = {}
    for name, fen, expected in EXTRA_PERFT:
        sample = chess.Board(fen)
        extra_observed[name] = {str(depth): perft(sample, depth) for depth in expected}
        assert extra_observed[name] == {str(k): v for k, v in expected.items()}

    # Same placement with different castling, en-passant and clock rights.
    castle = chess.Board()
    no_castle = chess.Board(castle.fen().replace(" KQkq ", " - "))
    assert canonical_key(castle, repetition_history(castle)) != canonical_key(no_castle, repetition_history(no_castle))
    ep = chess.Board("4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 1")
    no_ep = chess.Board("4k3/8/8/3pP3/8/8/8/4K3 w - - 0 1")
    assert canonical_key(ep, repetition_history(ep)) != canonical_key(no_ep, repetition_history(no_ep))
    clock = chess.Board("4k3/8/8/8/8/8/8/4K3 w - - 0 1")
    old_clock = chess.Board("4k3/8/8/8/8/8/8/4K3 w - - 4 3")
    assert canonical_key(clock, repetition_history(clock)) != canonical_key(old_clock, repetition_history(old_clock))

    # Reversible board cycle is not a canonical cycle: clock/history changed.
    cycle = chess.Board()
    initial_key = canonical_key(cycle, repetition_history(cycle))
    for uci in ("g1f3", "g8f6", "f3g1", "f6g8"):
        cycle.push_uci(uci)
    assert cycle.board_fen() == chess.Board().board_fen()
    assert canonical_key(cycle, repetition_history(cycle)) != initial_key
    assert cycle.is_repetition(2)

    # The judge is deterministic and never modifies the supplied board.
    board.push_uci("e2e4")
    before = board.fen()
    a = count_reachability(board, 2, "raw")
    b = count_reachability(board, 2, "raw")
    assert (a["k_sigma"], a["k_unique"], a["nodes"]) == (b["k_sigma"], b["k_unique"], b["nodes"])
    assert board.fen() == before
    assert 0 <= a["k_unique"] <= a["k_sigma"]
    simple = count_reachability(board, 2, "simple")
    assert simple["k_sigma"] == a["k_sigma"]
    return {"perft": observed, "extra_perft": extra_observed, "canonical_rights": "passed", "repetition": "passed", "determinism": "passed", "unique_bound": "passed", "raw_simple": "passed"}


def run_e1(output: Path, depths: tuple[int, ...], seed: int) -> None:
    output.mkdir(parents=True, exist_ok=True)
    for name in ("e1_first_moves.csv", "ga0_log.jsonl", "manifest.json"):
        if (output / name).exists():
            raise FileExistsError(f"Results already exist: {output / name}")
    script_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    e0 = run_e0()
    board = chess.Board(START_FEN)
    moves = sorted(move.uci() for move in board.legal_moves)
    assert len(moves) == 20
    rows = []
    for depth in depths:
        for uci in moves:
            board.push_uci(uci)
            local = board.legal_moves.count()
            metrics = count_reachability(board, depth, "raw")
            for mode in ("raw", "simple"):
                ks, ku = metrics["k_sigma"], metrics["k_unique"]
                row = {
                    "protocol": PROTOCOL, "fen": START_FEN, "side": "white",
                    "move": uci, "depth": depth, "mode": mode, "k_local": local,
                    "k_sigma": ks, "k_unique": ku,
                    "transposition_ratio": round(1 - ku / ks, 12) if ks else None,
                    # At a fixed exact depth every endpoint has the same turn.
                    "delta": ku if (depth % 2 == 1) else -ku,
                    "rho": ku + 1 if (depth % 2 == 1) else 1 / (ku + 1),
                    "min_reply_k_sigma": metrics["min_reply_k_sigma"],
                    "max_reply_k_sigma": metrics["max_reply_k_sigma"],
                    "nodes": metrics["nodes"],
                    "seconds": metrics["seconds"] if mode == "raw" else None,
                    "terminal_count": metrics["terminal"], "k_viable": None,
                    "complete": True,
                    "derived_from": None if mode == "raw" else "raw",
                    "seed": seed,
                }
                assert row["k_unique"] <= row["k_sigma"]
                rows.append(row)
                if mode == "raw":
                    print(f"d={depth} {uci}: KΣ={ks} KU={ku}", flush=True)
            board.pop()
    with (output / "e1_first_moves.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    with (output / "ga0_log.jsonl").open("w") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    manifest = {
        "protocol": PROTOCOL, "starting_fen": START_FEN, "depths": list(depths),
        "modes": ["raw", "simple"], "budget": "exhaustive at each depth",
        "simple_mode": "derived from raw: with full canonical key, an irreversible move cannot restore the same board and a reversible move strictly increments halfmove clock",
        "seed": seed, "script_sha256": script_hash,
        "chess_version": chess.__version__, "python_version": platform.python_version(),
        "e0": e0, "rows": len(rows),
        "k_viable": "unavailable: no exact tablebase or preregistered approximation",
        "canonical_key": "placement, turn, castling, legal en-passant, halfmove, repetition counts since last irreversible move",
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).parent / "results_e1")
    parser.add_argument("--e0-only", action="store_true")
    args = parser.parse_args()
    if args.e0_only:
        print(json.dumps(run_e0(), indent=2))
        return
    run_e1(args.output_dir, DEPTHS, seed=0)


if __name__ == "__main__":
    main()
