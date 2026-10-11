# Search integration and component ablations, v1 — 11 October 2026

This exploratory protocol is written before the new search results. Earlier chess results are known. It is not an independent preregistration and is not a test of all possible integrations.

## Question and common implementation

Can the frozen mobility rules improve move ordering inside the same Python chess search, including their feature cost in an equal wall-clock budget? The common engine uses iterative deepening, negamax alpha-beta, bounded capture/promotion quiescence with check evasions, tactical move ordering, killer/history ordering and a material/positional static evaluation. This is a transparent experimental engine, not a Stockfish modification or an industrial strength engine. No selective pruning, transposition table, opening book, tablebase or external engine is used in its decisions.

Only the root ordering of quiet moves changes. Previous-iteration best move and tactical priorities remain common. Full root metrics are computed once per move, without caching across trials; their cost is included. These experiments concern this root integration, not every node or changing the evaluation function.

Eight modes: baseline; A alone (minimise immediate legal replies); B alone (maximise minimum own legal moves after a reply); fixed ABC; observed opponent-effect switch; inferred opponent-rank switch; frozen GA2 weights; frozen GA0+GA1+GA2 weights. Both learned vectors are the existing March seed 100 vectors, not retrained on new tests. C and safety flags follow the frozen candidate-metrics implementation. A and B are explicit ablations, not redefinitions of the original theory.

## Corpus fixed without new engine outcomes

90 roots: 30 April endgames (six per 3–7-piece stratum, exclude terminal or claimable-draw roots, deterministic SHA-256 ranking); 30 Lichess tactical puzzles with at least 10 pieces (hash-rank among the first 2000 official CSV rows, distinct source games, after the opponent setup move); 30 June 2025 Broadcast middlegames (first eligible ply 40 per valid standard game with at least 16 pieces, hash rank, distinct games). Exclude FENs from March training and previous external corpora for the new tactical/middlegame roots. Puzzle first solution moves are external tactical references; no puzzle labels are used by the engine. Midgame reference is Stockfish 17.1, 100000 nodes, Threads 1, Hash 16, cleared per root, no Syzygy, all legal root moves ranked. Reference is approximate, not proven minimax truth.

Record source URLs, licenses, hashes, selection code, FEN, predecessor/last move, source game ID and solution line. Puzzles CC0; Broadcast CC BY-SA 4.0. Archive source prefixes and selected rows so later source changes cannot change frozen inputs. Selection from a prefix and Broadcast players is a convenience sample, not representative of all chess.

## Trials and outputs

Each root, mode and budget (50 ms and 200 ms) runs twice, with mode order rotated by root, budget and repetition. No simultaneous experimental searches. Single shared workstation, no isolation claim. Record chosen legal move, elapsed time, completed depth, search and quiescence nodes, feature preparation time, whether ordering finished, whether any depth completed, and interrupted stage. Deadline returns the last fully completed depth; if none completes, use lexicographically first legal move and label fallback. Deadline overruns are recorded. Trials with feature timeout are retained, not dropped.

Endgame quality: exact best-category preservation. Tactics: match the first supplied solution move (alternative solutions may exist). Middlegame: approximate reference-centipawn regret and top-move agreement; mate scores capped at 10000 for reporting. Do not call approximate engine agreement game-theoretic accuracy. Paired differences average repeated trials within each root; root bootstrap seed 20261011, 10000 draws, unadjusted 95% intervals. Multiple variants/budgets are exploratory; no significance or universal superiority claim from isolated intervals.

Fixed-depth control: first four hash-ranked roots per group, depth 2, 5 s safety ceiling. Compare scores only when depth completed; different tied optimal moves are permitted. With identical leaf evaluation and full-width alpha-beta, scores must agree across modes. Record elapsed time and nodes, including feature cost. Safety timeouts are missing depth-control measurements, not evidence of equal scores.

## Continuations from initial/opening positions

Seven candidates (all above except GA2) versus the same baseline search, equal 25 ms per move, sides exchanged. Five paired starts: initial position plus four distinct 8-ply prefixes hash-selected from the existing CC0 opening catalog. Thus 70 games, 10 per candidate. All begin at the initial position; four sets use a common forced prefix. Record full UCI and PGN histories, per-move timing/depth/fallback, legal replay, exact natural termination. Ceiling 240 plies after the prefix. An unfinished game is **unresolved**, not a draw, win or engine adjudication. Report actual W/D/L and unresolved counts; score bounds assign unresolved games 0 or 1. This short low-budget experiment cannot establish an Elo rating or long-time-control strength.

## Reproduction

Run in a fresh venv/copy using saved inputs; independently replay every move and recompute summaries. This clean-environment rerun by the same assistant is an engineering check, not independent scientific replication. Preserve public v1.0.0 unchanged; package new evidence separately.

Preflight corrections before the final comparison: reject terminal roots; poll search deadlines at safe board-stack checkpoints. Retain aborted preflight logs separately. Source selection corrections are recorded in the manifest.
