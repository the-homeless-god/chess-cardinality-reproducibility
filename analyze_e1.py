"""Describe the frozen first-move series without selecting a winning metric."""

from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path(__file__).parent


def main() -> None:
    result_dir = ROOT / "results_e1"
    manifest = json.loads((result_dir / "manifest.json").read_text())
    with (result_dir / "e1_first_moves.csv").open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert manifest["rows"] == len(rows) == 160
    raw = [row for row in rows if row["mode"] == "raw"]
    assert len(raw) == 80
    for depth in manifest["depths"]:
        group = [row for row in raw if int(row["depth"]) == depth]
        assert len(group) == 20
        print(f"Depth {depth}: ΣKΣ={sum(int(row['k_sigma']) for row in group)}")
        for metric in ("k_sigma", "k_unique"):
            max_value = max(int(row[metric]) for row in group)
            leaders = sorted(row["move"] for row in group if int(row[metric]) == max_value)
            e4 = next(int(row[metric]) for row in group if row["move"] == "e2e4")
            print(f"  {metric}: max={max_value}, leaders={','.join(leaders)}, e2e4={e4}")
    print("All rankings are descriptive; no WDL or K^V verdict is available.")


if __name__ == "__main__":
    main()
