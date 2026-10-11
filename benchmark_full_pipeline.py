"""Time the complete local GA training and held-out inference pipeline."""

from __future__ import annotations

import hashlib
import json
import random
import statistics
import time
from pathlib import Path

from run_ga_experiment import POSITIONS, RESPONSES, SEEDS, choice, prepare, run_mode

ROOT = Path(__file__).parent
OUT = ROOT / "results_full_game_runtime"
MODES = ("GA2", "GA1+GA2", "GA0+GA1+GA2")


def percentile(items: list[float], p: float) -> float:
    values = sorted(items)
    at = (len(values) - 1) * p
    lo = int(at)
    hi = min(lo + 1, len(values) - 1)
    return values[lo] + (values[hi] - values[lo]) * (at - lo)


def paired_bootstrap(rows: list[dict], key: str) -> dict:
    by_seed = {seed: {} for seed in SEEDS}
    for row in rows:
        by_seed[row["seed"]][row["mode"]] = row[key]
    diffs = [by_seed[seed]["GA1+GA2"] - by_seed[seed]["GA0+GA1+GA2"]
             for seed in SEEDS]
    ratios = [by_seed[seed]["GA0+GA1+GA2"] / by_seed[seed]["GA1+GA2"]
              for seed in SEEDS]
    rng = random.Random(20261004)
    boot = [statistics.mean(rng.choices(diffs, k=len(diffs))) for _ in range(10000)]
    return {"paired_savings_mean_seconds": statistics.mean(diffs),
            "paired_savings_ci95_seconds": [percentile(boot, 0.025), percentile(boot, 0.975)],
            "paired_ratio_median": statistics.median(ratios),
            "paired_ratios": ratios}


def main() -> None:
    if OUT.exists():
        raise FileExistsError(OUT)
    OUT.mkdir()
    rows = []
    for seed in SEEDS:
        # Rotate the run order so drift in clock or temperature is shared.
        mode_order = MODES[seed % 3:] + MODES[:seed % 3]
        for mode in mode_order:
            started = time.perf_counter()
            data = prepare()
            prepared = time.perf_counter()
            train = [row for row in data if row["split"] == "train"]
            val = [row for row in data if row["split"] == "val"]
            test = [row for row in data if row["split"] == "test"]
            run = run_mode(mode, seed, train, val)
            trained = time.perf_counter()
            selected = [choice(row, run["weights"]) for row in test]
            finished = time.perf_counter()
            inference_repeats = []
            for _ in range(5):
                again = time.perf_counter()
                check = [choice(row, run["weights"]) for row in test]
                assert check == selected
                inference_repeats.append(time.perf_counter() - again)
            row = {
                "seed": seed, "mode": mode, "prepare_seconds": prepared - started,
                "train_seconds": trained - prepared,
                "inference_seconds": finished - trained,
                "end_to_end_seconds": finished - started,
                "inference_50_repeat_seconds": inference_repeats,
                "fitness_evaluations": run["fitness_evaluations"],
                "validation_evaluations": run["validation_evaluations"],
                "test_optimal_fraction": statistics.mean(
                    test[index]["scores"][picked] == test[index]["best"]
                    for index, picked in enumerate(selected)),
            }
            rows.append(row)
            (OUT / "runs.json").write_text(json.dumps(rows, indent=2) + "\n")
            print(seed, mode, "total", round(row["end_to_end_seconds"], 3),
                  "fit", round(row["train_seconds"], 3), flush=True)
    modes = {}
    for mode in MODES:
        subset = [row for row in rows if row["mode"] == mode]
        modes[mode] = {
            key: {"mean": statistics.mean(row[key] for row in subset),
                  "median": statistics.median(row[key] for row in subset),
                  "range": [min(row[key] for row in subset), max(row[key] for row in subset)]}
            for key in ("prepare_seconds", "train_seconds", "inference_seconds",
                        "end_to_end_seconds", "fitness_evaluations", "test_optimal_fraction")
        }
        modes[mode]["inference_50_repeat_median_seconds"] = statistics.median(
            value for row in subset for value in row["inference_50_repeat_seconds"])
    summary = {"protocol": "full-game-and-runtime-protocol-v1",
               "positions_sha256": hashlib.sha256(POSITIONS.read_bytes()).hexdigest(),
               "responses_sha256": hashlib.sha256(RESPONSES.read_bytes()).hexdigest(),
               "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               "seed_count": len(SEEDS), "modes": modes,
               "paired_total": paired_bootstrap(rows, "end_to_end_seconds"),
               "paired_training": paired_bootstrap(rows, "train_seconds")}
    (OUT / "runtime_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print("summary", json.dumps(summary["paired_total"]), flush=True)


if __name__ == "__main__":
    main()
