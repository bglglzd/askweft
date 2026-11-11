# Synthetic corpus v1

30 development inputs D, 10 originally held-out inputs H and 8 separate stress inputs S.
The manifest seals all 144 native input/oracle/settings files. Case JSON is the planner input;
settings contain budgets; gold and future primitive answers exist only in oracle files.
The split/bytes were sealed before product evaluation. No customer records are included.

The original `HOLDOUT_DO_NOT_OPEN` folder name records its prepublication role. These files
are now published, so every public rerun is a regression, not fresh held-out evidence. The
implementation author did not inspect H before a separate evaluator saved its first run.
This was role separation in a shared workspace, not a hermetic security boundary.

Each oracle has one immutable value/null per primitive field, independent of policy/menu/
seed. Main gold alternatives are financially feasible and survive initial confirmed values;
nonnull oracle values agree with their gold predictions. Null may mean the operator cannot
supply confirmation. Expectations are invariants or explicitly scoped allowed state sets.
Policies can legitimately differ under constrained budgets.

S01–S03 cover unsupported currency, no financial alternative and contradictory observations.
S04–S07 deliberately contain truncated JSON, duplicate keys, a nonfinite number and a float
amount. Pass these exact bytes to the importer; do not repair or reserialize them first.
S08 is one input with three fresh-session configurations: unknown evidence, zero-question
budget and zero-field budget. Report 8 independent stress inputs and 10 scoped subruns.

The question/configuration contract is [preregistered](../../docs/preregistration-v1.md).
[First results](../first-results/summary.json), [comparison](../../docs/evaluation.md) and
[replay commands](../../docs/evaluation-replay.md) preserve the separate D/H/S denominators,
all-case effort, conditional metrics and random-seed repeats. Twenty seeds do not create
twenty times more independent cases. A wrong singleton counts wrong and is never vetoed by gold.

Do not rewrite sealed labels after observing outputs. Corrections require a separately
versioned erratum/corpus with chronology. Synthetic data is offered under CC0-1.0; see LICENSE.
