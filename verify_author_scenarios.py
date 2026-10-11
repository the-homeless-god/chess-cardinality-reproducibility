"""Reproduce the move counts in the author's opening thought experiment.

Potential mobility of the side not to move is counterfactual: only its turn
is changed, and en passant is cleared. It is not a legal game continuation.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import chess


ROOT = Path(__file__).parent
OUTPUT = ROOT / "results_author_scenarios"
TABLEBASE = ROOT / "results_endgame_2025_03" / "responses.jsonl"
LINES = {
    "initial": [],
    "Nf3": ["g1f3"],
    "Nc3": ["b1c3"],
    "e4": ["e2e4"],
    "Nf3 Nf6": ["g1f3", "g8f6"],
    "Nf3 Nf6 Ne5": ["g1f3", "g8f6", "f3e5"],
    "Nf3 Nf6 Ne5 d6": ["g1f3", "g8f6", "f3e5", "d7d6"],
    "Nf3 Nf6 Ne5 d6 Nc4": ["g1f3", "g8f6", "f3e5", "d7d6", "e5c4"],
    "Nf3 Nf6 Ne5 d6 Nxf7": ["g1f3", "g8f6", "f3e5", "d7d6", "e5f7"],
}


def mobility(board: chess.Board, color: chess.Color) -> dict:
    probe = board.copy()
    counterfactual = probe.turn != color
    probe.turn = color
    if counterfactual:
        probe.ep_square = None
    by_piece = Counter(
        chess.piece_symbol(probe.piece_type_at(move.from_square))
        for move in probe.legal_moves
    )
    return {
        "count": probe.legal_moves.count(),
        "by_piece": dict(sorted(by_piece.items())),
        "counterfactual_turn_change": counterfactual,
    }


def main() -> None:
    rows = []
    for name, uci_moves in LINES.items():
        board = chess.Board()
        for uci in uci_moves:
            move = chess.Move.from_uci(uci)
            if move not in board.legal_moves:
                raise ValueError(f"Illegal move in {name}: {uci}")
            board.push(move)
        row = {
            "line": name,
            "uci": uci_moves,
            "fen": board.fen(en_passant="legal"),
            "actual_turn": "white" if board.turn else "black",
            "actual_legal_moves": board.legal_moves.count(),
            "white_potential": mobility(board, chess.WHITE),
            "black_potential": mobility(board, chess.BLACK),
            "black_castling_rights": board.has_kingside_castling_rights(chess.BLACK)
            or board.has_queenside_castling_rights(chess.BLACK),
        }
        if name.endswith("Nxf7"):
            row["Kxf7_legal"] = chess.Move.from_uci("e8f7") in board.legal_moves
            after = board.copy()
            after.push_uci("e8f7")
            row["black_castling_rights_after_Kxf7"] = (
                after.has_kingside_castling_rights(chess.BLACK)
                or after.has_queenside_castling_rights(chess.BLACK)
            )
        rows.append(row)
    OUTPUT.mkdir(exist_ok=True)
    item = next(
        record for record in (json.loads(line) for line in TABLEBASE.read_text().splitlines())
        if record["position_id"] == "B202503-144"
    )
    board = chess.Board(item["fen"])
    root_opponent = mobility(board, chess.BLACK)["count"]
    api_moves = {move["uci"]: move for move in item["response"]["moves"]}
    counterexample_moves = {}
    for uci in ("c5f8", "b7b6"):
        candidate = chess.Move.from_uci(uci)
        assert candidate in board.legal_moves
        after = board.copy()
        after.push(candidate)
        counterexample_moves[uci] = {
            "san": board.san(candidate),
            "opponent_legal_moves": after.legal_moves.count(),
            "api_category_for_next_player": api_moves[uci]["category"],
        }
    counterexample = {
        "position_id": item["position_id"],
        "fen": item["fen"],
        "root_category_for_white": item["response"]["category"],
        "black_potential_before_white_move": root_opponent,
        "moves": counterexample_moves,
    }
    assert counterexample["root_category_for_white"] == "win"
    assert counterexample_moves["c5f8"]["opponent_legal_moves"] == 3
    assert counterexample_moves["c5f8"]["api_category_for_next_player"] == "draw"
    assert counterexample_moves["b7b6"]["opponent_legal_moves"] == 5
    assert counterexample_moves["b7b6"]["api_category_for_next_player"] == "loss"
    (OUTPUT / "verification.json").write_text(
        json.dumps({"library": f"python-chess {chess.__version__}", "rows": rows,
                    "scenario_a_counterexample": counterexample},
                   ensure_ascii=False, indent=2) + "\n"
    )
    for row in rows:
        print(row["line"], row["white_potential"]["count"],
              row["black_potential"]["count"], row["actual_legal_moves"])


if __name__ == "__main__":
    main()
