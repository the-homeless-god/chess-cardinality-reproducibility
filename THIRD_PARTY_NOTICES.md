# Rights and attribution

This release is publicly available research material. No new blanket license is assigned to Marat F. Zimnurov's original scripts in this release. Public access alone does not grant general redistribution or commercial-use rights. Contact the author for permissions beyond rights provided by applicable law.

- `data/openings/`: Lichess chess-openings, commit 5a13018164f6bd88f48b3dc31a8e2a39f31a060a, CC0. Original COPYING.txt is retained. https://github.com/lichess-org/chess-openings
- Broadcast-derived selected FENs and contexts: Lichess and original broadcast providers, March–June 2025. CC BY-SA 4.0 as stated by https://database.lichess.org/broadcast/. Game-level URLs and archive hashes are retained in each data directory. Thirty selected June source games are retained as PGN with original headers; no complete monthly archive is redistributed. See https://creativecommons.org/licenses/by-sa/4.0/.
- Saved Syzygy API responses: attributed to Lichess lila-tablebase and Syzygy. https://github.com/lichess-org/lila-tablebase. They are factual analysis records; no additional license from this author is asserted over third-party responses.
- python-chess 1.999 / chess 1.11.2: dependency, GPL-3.0-or-later; not vendored. https://github.com/niklasf/python-chess
- Stockfish 17.1: optional external engine, GPLv3. Official source and binary release: https://github.com/official-stockfish/Stockfish/releases/tag/sf_17.1. Not bundled. Download instructions retain the official release including its source and COPYING notice. Binary provenance and hashes are recorded in results_extended/environment.json.

The private dissertation, correspondence, program registration certificate and unrelated projects are outside this public package.

- `data/search_integration_v1/puzzle-source-prefix.csv` and derived tactical roots: official Lichess puzzle database, CC0, source snapshot and hash in manifest.json. https://database.lichess.org/#puzzles. Tactical solution lines are external reference data, not generated claims.
- zstandard 0.25.0 is an optional corpus-preparation dependency, not vendored; its upstream license terms apply. Ordinary replay does not require it. https://github.com/indygreg/python-zstandard.
