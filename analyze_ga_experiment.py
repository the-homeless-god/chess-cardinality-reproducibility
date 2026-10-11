"""Paired holdout analysis with positions as bootstrap sampling units."""

import collections
import hashlib
import json
import random
import statistics
from pathlib import Path

ROOT = Path(__file__).parent / "results_ga_2025_03"
DATA = json.loads((ROOT / "features.json").read_text())
RUNS = json.loads((ROOT / "runs.json").read_text())
TEST = [r for r in DATA if r["split"] == "test"]
MODES = ["random", "max_kappa", "min_kappa", "max_ku2", "material",
         "GA2", "GA1+GA2", "GA0+GA1+GA2"]
SEEDS = range(100, 110)


def metric(row, run):
    score = row["scores"][run["test_choices"][row["id"]]]
    return {"optimal": int(score == row["best"]), "regret": row["best"] - score,
            "preserved": int(score == row["best"]) if row["best"] > 0 else None}


def distribution(mode, field="optimal", informative=False):
    rows = [r for r in TEST if not informative or r["informative"]]
    selected = [r for r in RUNS if r["mode"] == mode]
    return [statistics.mean(metric(row, run)[field] for run in selected)
            for row in rows]


def ci_diff(a, b, informative=False):
    xs = distribution(a, informative=informative)
    ys = distribution(b, informative=informative)
    diff = [x-y for x,y in zip(xs,ys)]
    rng = random.Random(20261004)
    samples = []
    for _ in range(10000):
        samples.append(statistics.mean(rng.choice(diff) for _ in diff))
    samples.sort()
    return {"difference": statistics.mean(diff), "ci95": [samples[250],samples[9749]],
            "positions": len(diff)}


def main():
    summary = {"split_counts": collections.Counter(r["split"] for r in DATA),
               "test_root_categories": collections.Counter(r["root_category"] for r in TEST),
               "test_informative": sum(r["informative"] for r in TEST),
               "test_best_scores": collections.Counter(str(r["best"]) for r in TEST),
               "modes": {}, "paired_differences": {}}
    for mode in MODES:
        runs = [r for r in RUNS if r["mode"] == mode]
        acc = [statistics.mean(metric(row, run)["optimal"] for row in TEST) for run in runs]
        informative = [row for row in TEST if row["informative"]]
        acc_inf = [statistics.mean(metric(row, run)["optimal"] for row in informative) for run in runs]
        regret = [statistics.mean(metric(row, run)["regret"] for row in TEST) for run in runs]
        summary["modes"][mode] = {
            "accuracy_mean": statistics.mean(acc), "accuracy_range": [min(acc), max(acc)],
            "informative_accuracy_mean": statistics.mean(acc_inf),
            "regret_mean": statistics.mean(regret),
            "fitness_evaluations_mean": statistics.mean(r["fitness_evaluations"] for r in runs),
            "fitness_evaluations_range": [min(r["fitness_evaluations"] for r in runs),
                                          max(r["fitness_evaluations"] for r in runs)],
        }
    for a,b in [("GA0+GA1+GA2","GA2"),("GA0+GA1+GA2","GA1+GA2"),
                ("GA0+GA1+GA2","min_kappa"),("GA0+GA1+GA2","material"),
                ("min_kappa","max_kappa"),("max_ku2","random")]:
        summary["paired_differences"][a+" - "+b] = {
            "all": ci_diff(a,b), "informative": ci_diff(a,b,informative=True)}
    summary["ga0_early_stop_runs"] = sum(r["stop"] == "threshold_plateau" for r in RUNS
                                         if r["mode"] == "GA0+GA1+GA2")
    summary["source_sha256"] = {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
                                for name in ("features.json","runs.json")}
    (ROOT / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
