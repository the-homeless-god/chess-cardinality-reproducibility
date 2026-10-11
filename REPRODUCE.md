# Reproduction commands

Python 3.10+ on macOS or Linux. Timed runners use POSIX signals. Engine build, dependency versions and input hashes are recorded in the environment files and manifests.

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python verify_reproduction.py
python verify_search_integration.py
```

These commands verify saved labels, legal game traces and numerical summaries offline. To recompute fixed-depth controls:

```sh
python verify_search_integration.py --repeat-fixed-depth --report /tmp/search-verification.json
```

## Engine computation

Stockfish 17.1 is not bundled. Obtain the matching official binary: https://github.com/official-stockfish/Stockfish/releases/tag/sf_17.1 . The pinned macOS ARM64 download is available through `python download_stockfish.py`.

Run in a separate copy. Runners can rewrite output files, which will no longer match the reference checksums. Do not run simultaneous timed experiments.

```sh
python run_extended_comparisons.py --engine /absolute/path/to/stockfish --stage controls
python run_extended_comparisons.py --engine /absolute/path/to/stockfish --stage april
python run_extended_comparisons.py --engine /absolute/path/to/stockfish --stage games
python benchmark_extended_pipeline.py
python run_search_integration.py --engine /absolute/path/to/stockfish --stage all
python analyze_search_integration.py
```

The search runner resumes saved records. To recompute timed records, move `results_search_integration_v1/` aside in the separate copy. Target budgets include feature construction; actual overruns are retained. Wall times and time-limited choices may vary by machine and workload.

## Inputs and protocols

- `data/*/SOURCE.md` and manifests: sources, selection and hashes.
- `ga-experiment-protocol.md`: weight fitting and budget controls.
- `scenario-comparison-protocol.md`: conditional-policy definitions.
- `full-game-and-runtime-protocol.md`: continuations and timing.
- `extended-comparison-protocol.md`: external-engine comparisons.
- `search-integration-protocol.md`: root-ordering trials and depth controls.

Corpus preparation needs network access and optional `zstandard==0.25.0`. Saved inputs allow offline replay without downloading replacement datasets. Preserve the source licenses and provenance when redistributing input records.
