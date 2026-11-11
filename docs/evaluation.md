# Synthetic policy comparison

The first experiment used 30 development inputs, 10 held-out inputs and 8 separate stress inputs. Its question menu, exact score/ties, costs, budgets, seeds and summaries were fixed before corpus outputs. A separate curator sealed inputs/oracles before implementation execution. The implementation author did not inspect H until a separate evaluator completed and saved its first result. This separation used roles in a shared workspace, not a hermetic access-control boundary.

Default lambda 1:

| Split | Policy | Independent inputs | Runs | Correct resolved | Unresolved | Questions median/p90, all cases | Questions median/p90, correct only | Fields median/p90 | Declared cost median/p90 |
| --- | --- | ---: | ---: | ---: | ---: | --- | --- | --- | --- |
| D | Adaptive |30|30|24|6|1/2|1/2|1/2|2/5|
| D | Fixed |30|30|23|7|1/2|1/3|1/2|2/6|
| D | Random |30|600|480|120|1/2|1/2|1/4|3/8|
| H | Adaptive |10|10|7|3|1.5/3|2/3|1.5/3|3.5/8|
| H | Fixed |10|10|7|3|1.5/3|2/3|1.5/3|3.5/8|
| H | Random |10|200|132|68|1/3|1/2|2/4|5/9|

There were zero wrong resolutions and zero expectation/execution failures on the authored D/H cases. Unknown and exhausted-budget cases remain in all-case effort statistics. Correct-only denominators are the stated correct-resolution counts. Random uses 20 seeds over the same inputs; its rows are repeated runs, not extra independent cases. Full per-seed variation, budget groups and all trajectories are in [full results](../benchmarks/first-results/).

The default held-out aggregate matches fixed; this does not establish a default held-out advantage. Random's lower H question median accompanies a higher unresolved rate and more fields/cost. Do not judge effort from the conditional question median alone.

Lambda 0 and 4 were preregistered sensitivity settings. On H, lambda 0 adaptive and fixed each resolve 7/10; adaptive uses question median/p90 of 1/1 versus fixed 1.5/3, with field p90 of 4 versus 3. Lambda 4 adaptive and fixed each resolve 7/10 and have question median/p90 of 1.5/3. Default lambda 1 was retained. No uniform policy advantage or global optimality follows.

The stress set has 8 independent inputs and 10 named input/configuration subruns because one input has 3 separately scoped budget/unknown variants. Its 660 repeated runs contain 264 expected invalid-import refusals with empty fresh state and 396 expected unresolved outcomes, with no expectation failures. Stress has a separate denominator.

The evaluated core commit was `ecabf2e39d3818d6ceeabe94e673d07f4161f35f`. First H used a tested preliminary core wheel and a verified source/config/evaluator/corpus/toolchain/artifact freeze. That wheel was not the final release artifact. Final release evidence must separately verify unchanged domain/planner/store/worker hashes and validate final packaging/UI. [summary](../benchmarks/first-results/summary.json) records the exact evaluated core hashes, original result digests and experiment configuration.

Actual elapsed D/H/S evaluation times were 71.616224/28.045008/12.110521 seconds on Python 3.11.15, Windows AMD64, Intel64 Family 6 Model 151 Stepping 2. These timings include local worker, SQLite and process/filesystem overhead. Declared field cost is not measured time or money.

These small authored synthetic sets do not establish customer savings or general document accuracy. Resolution is conditional on supplied alternatives; an outside truth that mimics one of them may be undetectable. After publication, all corpus reruns are regression evaluations. See [replay instructions](evaluation-replay.md) for the commands.
