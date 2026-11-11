# Replaying the synthetic comparison

The published corpus contains 30 development inputs, 10 originally held-out inputs and 8 stress inputs. Once published, every rerun is a regression evaluation. The replay tool always records `evaluation_class: published_regression` and `fresh_heldout_claim: false`. New held-out evidence requires a new independently authored, previously uninspected set.

The planner worker receives source JSON and public settings. It then receives only the primitive answer keys for its pending request. Gold and future answers remain in the evaluator. Adaptive, fixed and random use the same feasible menu, budgets and unknown-answer handling. Random seeds 0–19 repeat the same inputs; they are not extra independent cases. Stress subruns retain their original input denominator.

Use Python 3.11+ from an installed development checkout. Keep output and freeze files outside the checkout so the source stays unchanged:

```console
python tools/evaluate.py --split D --output ../askweft-results/D
python tools/evaluate.py --split S --output ../askweft-results/S
```

The comparison runs lambda 0, 1 and 4 separately. Per-case settings provide the same question and field budgets to all policies. Reports contain every trajectory, unknown/refused outcomes, all-case and correct-resolution-only effort, median/p90 denominators, wrong/unresolved counts, per-seed variation and budget groups. Empty conditional groups have null metrics. Cost is declared field effort.

To replay H, first bind a clean source commit, interpreter and a local release artifact. This is a reproducibility freeze of already published data, not a new blind evaluation:

```console
python tools/evaluate.py --prepare-freeze ../askweft-results/replay-freeze.json --artifact /path/to/downloaded/askweft-0.1.0-py3-none-any.whl
python tools/evaluate.py --split H --output ../askweft-results/H --freeze-record ../askweft-results/replay-freeze.json
```

`--python PATH` selects the worker interpreter and must match between preparation and execution. The tool verifies original contract/manifest seals, exact source/evaluator/config/artifact bytes and toolchain before H access, then every sealed file before parsing cases. The manifest's original `HOLDOUT_DO_NOT_OPEN` directory name records its prepublication role; the data is now public. A mismatch is a refusal, not an invitation to repair sealed labels.

The output directory must be new. Each run and worker exchange is flushed as it happens. Interrupted or failed first outputs remain intact; choose a separately named regression directory for a later run. A wrong singleton ends its run and counts as wrong. Unknown and exhausted-budget cases stay in all-case effort statistics. Import failures are passed through unchanged and checked for an empty fresh session.

Only exact matches within the finite supplied model can resolve. An outside truth that mimics a supplied alternative cannot always be detected. These authored synthetic inputs do not establish customer savings or general document accuracy.
