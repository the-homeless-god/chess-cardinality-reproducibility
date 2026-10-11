"""Paired April validation of observed and inferred opponent classifiers."""

from __future__ import annotations

import collections
import hashlib
import json
import random
import statistics
from pathlib import Path

import chess

ROOT = Path(__file__).parent / "results_scenarios_2025_04"
SCORE = {"win": 2, "cursed-win": 1, "draw": 1, "blessed-loss": 1, "loss": 0}
MODES = ("observed", "inferred", "neutral", "min_kappa")


def bootstrap(xs: list[float]) -> dict:
    rng = random.Random(20261004)
    estimates = sorted(statistics.mean(rng.choice(xs) for _ in xs)
                       for _ in range(10000))
    return {"mean": statistics.mean(xs), "ci95": [estimates[250], estimates[9749]],
            "positions": len(xs)}


def main() -> None:
    predictions_path = ROOT / "predictions.json"
    responses_path = ROOT / "responses.jsonl"
    frozen = json.loads((ROOT / "prediction_manifest.json").read_text())
    collected = json.loads((ROOT / "response_manifest.json").read_text())
    assert hashlib.sha256(predictions_path.read_bytes()).hexdigest() == frozen["predictions_sha256"]
    assert collected["predictions_sha256_before_labels"] == frozen["predictions_sha256"]
    assert hashlib.sha256(responses_path.read_bytes()).hexdigest() == collected["responses_sha256"]
    predictions = json.loads(predictions_path.read_text())
    labels = {item["position_id"]: item["response"]
              for item in (json.loads(line) for line in responses_path.read_text().splitlines())}
    assert len(predictions) == len(labels) == 250
    rows = []
    excluded = []
    for prediction in predictions:
        response = labels[prediction["position_id"]]
        categories = {move["category"] for move in response["moves"]}
        if not categories <= SCORE.keys() or response["category"] not in SCORE:
            excluded.append({"position_id": prediction["position_id"],
                             "root": response["category"], "move_categories": sorted(categories)})
            continue
        by_move = {move["uci"]: 2 - SCORE[move["category"]] for move in response["moves"]}
        assert set(by_move) == {item["uci"] for item in prediction["candidates"]}
        best = max(by_move.values())
        row = {
            "position_id": prediction["position_id"],
            "pieces": len(chess.Board(prediction["fen"]).piece_map()),
            "root_category": response["category"],
            "best_score": best, "informative": len(set(by_move.values())) > 1,
            "observed_class": prediction["observed_class"],
            "inferred_class": prediction["inferred_class"],
            "same_choice": prediction["choices"]["observed"] == prediction["choices"]["inferred"],
            "seconds": prediction["seconds"],
            "replies_analyzed": prediction["context"]["replies_analyzed"],
        }
        for mode in MODES:
            uci = prediction["choices"][mode]
            row[mode] = {
                "uci": uci, "score": by_move[uci],
                "optimal": int(by_move[uci] == best),
                "regret": best - by_move[uci],
            }
        rows.append(row)
    assert rows
    summary = {
        "protocol": "scenario-comparison-protocol-v1",
        "positions_total": len(predictions), "positions_primary": len(rows),
        "excluded_positions": excluded,
        "root_categories": dict(collections.Counter(r["root_category"] for r in rows)),
        "informative_positions": sum(r["informative"] for r in rows),
        "class_counts": {
            name: dict(collections.Counter(r[name + "_class"] for r in rows))
            for name in ("observed", "inferred")
        },
        "class_agreement": statistics.mean(r["observed_class"] == r["inferred_class"] for r in rows),
        "choice_agreement": statistics.mean(r["same_choice"] for r in rows),
        "different_choice_positions": sum(not r["same_choice"] for r in rows),
        "different_choice_informative": sum(not r["same_choice"] and r["informative"] for r in rows),
        "modes": {}, "paired": {},
        "mean_policy_seconds": statistics.mean(r["seconds"] for r in rows),
        "mean_replies_analyzed": statistics.mean(r["replies_analyzed"] for r in rows),
    }
    for mode in MODES:
        summary["modes"][mode] = {
            "optimal_all": statistics.mean(r[mode]["optimal"] for r in rows),
            "optimal_informative": statistics.mean(r[mode]["optimal"] for r in rows if r["informative"]),
            "regret": statistics.mean(r[mode]["regret"] for r in rows),
            "optimal_by_pieces": {
                str(pieces): statistics.mean(r[mode]["optimal"] for r in rows if r["pieces"] == pieces)
                for pieces in range(3, 8)
            },
        }
        differing = [r for r in rows if not r["same_choice"]]
        summary["modes"][mode]["optimal_when_variants_choose_differently"] = (
            statistics.mean(r[mode]["optimal"] for r in differing) if differing else None
        )
    for a, b in (("observed", "inferred"), ("observed", "neutral"),
                 ("inferred", "neutral"), ("observed", "min_kappa"),
                 ("inferred", "min_kappa")):
        all_differences = [r[a]["optimal"] - r[b]["optimal"] for r in rows]
        informative = [r[a]["optimal"] - r[b]["optimal"] for r in rows if r["informative"]]
        summary["paired"][f"{a}-{b}"] = {
            "all": bootstrap(all_differences), "informative": bootstrap(informative),
            "a_only_optimal": sum(r[a]["optimal"] and not r[b]["optimal"] for r in rows),
            "b_only_optimal": sum(r[b]["optimal"] and not r[a]["optimal"] for r in rows),
        }
    (ROOT / "analysis_rows.json").write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n")
    (ROOT / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
