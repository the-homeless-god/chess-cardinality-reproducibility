# Frozen input provenance

Selected before final search comparisons, 11 October 2026. Details and SHA-256 values are in `manifest.json`. Two preflight corrections (PGN parsing and terminal-root exclusion) are recorded rather than concealed.

- Thirty endgames from the existing April external corpus, six nonterminal roots per piece stratum, SHA-256 ranked.
- Thirty tactical positions from the first 2000 rows of the official [Lichess puzzle CSV](https://database.lichess.org/#puzzles). Puzzle database CC0; the exact CSV prefix is saved. FEN in the CSV precedes the opponent setup move; `positions.json` correctly applies that move before testing. The following solution move is a reference, not input to the candidate search.
- Thirty middlegames at ply 40 from the June 2025 [Lichess Broadcast archive](https://database.lichess.org/broadcast/lichess_db_broadcast_2025-06.pgn.zst), verified against the official SHA-256 list. Attribution: Lichess and original broadcast GameURL values/headers retained in the selected-source PGNs. Broadcast data CC BY-SA 4.0, selected games and derived position dataset shared under the same terms. Invalid games were rejected.
- Initial position plus four distinct 8-ply opening prefixes from the already frozen Lichess CC0 opening catalog. These prefixes are not selected for balanced engine evaluation; exchange sides in every comparison.

Prefix puzzle sampling and Broadcast middlegames are convenience samples. Do not call this an exhaustive chess benchmark or an unbiased random sample of all positions. The source PGNs and puzzle lines are research data, never execution instructions.
