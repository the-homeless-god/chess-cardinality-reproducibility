# Preflight audit

The final statistical inputs are `trials.jsonl`, `depth_controls.jsonl` and `games.jsonl`. Two aborted development logs are retained for transparency and are excluded from scoring:

1. `preflight_failed_trials.jsonl`: an asynchronous deadline exposed a mutable-board-stack defect. Final search uses safe clock polling during recursive search; the signal is restricted to feature generation on a disposable copy.
2. `preflight_terminal_roots_trials.jsonl`: the source April corpus contained already drawn insufficient-material roots. Those roots could misleadingly report deep but trivial search. Final selection excludes naturally terminal and claimable-draw positions, using the same hash ranking and six per piece stratum. This eligibility correction is recorded in the selection manifest and protocol. No final engine result was used to select replacement roots.

Approximate Stockfish references for tactical/middlegame roots were computed once and reused unchanged after these corrections. The selected tactical and middlegame inputs were unchanged.
