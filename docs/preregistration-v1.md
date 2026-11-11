# Askweft v0.1 domain and evaluation contract

Frozen2026-11-11 after bounded preimplementation consistency review. No implementation, corpus or product outputs existed at freeze. The clarifications below are part of this version and take precedence where they make the initial text more precise. Root owns implementation. This is document clarification planning over a finite supplied interpretation set, not OCR, automatic bank matching, credit approval or an accounting system.

## User and journey

An operations specialist imports extracted invoice and bank-event JSON plus explicitly proposed candidate record groups. Several groups are financially compatible but differ in reference, settlement date, counterparty or duplicate status. Askweft ranks a fixed menu of field requests, shows each answer partition and its declared cost, records actual answers and narrows the candidates. One remaining candidate is resolved **within the supplied model**; no external financial action follows. A contradictory answer, unsupported case or exhausted evidence/budget remains unresolved. Start a new session from preserved original input to correct a mistaken answer; v0.1 does not silently rewrite past answers.

## Case format and constraints

One UTF-8 JSON object, closed keys, duplicate keys/nonfinite numbers refused, maximum256KiB. Format:

```json
{
  "format": 1,
  "id": "case-001",
  "title": "Synthetic invoice example",
  "invoice": {
    "id": "INV-1",
    "amount_minor": 10000,
    "currency": "USD",
    "issued_on": "2030-01-01",
    "reference": null,
    "party_key": "north-harbor"
  },
  "bank_events": [
    {"id":"B1","amount_minor":10000,"currency":"USD","booked_on":"2030-01-02","reference":"PAY-A","party_key":"north-harbor"},
    {"id":"B2","amount_minor":10000,"currency":"USD","booked_on":"2030-01-03","reference":"PAY-B","party_key":"north-harbor"}
  ],
  "alternatives": [
    {"id":"A","bank_ids":["B1"]},
    {"id":"B","bank_ids":["B2"]}
  ],
  "confirmed": {}
}
```

- Exactly one invoice,0–16 bank events and0–16 alternatives. An alternative selects1–4 distinct existing bank IDs, sorted canonically. Duplicate selected-record sets are refused even under different alternative IDs. IDs are case-sensitive ASCII `[A-Za-z0-9][A-Za-z0-9_.-]{0,63}`; all document/alternative IDs unique in their respective namespaces. Title is optional, presentation only, at most120characters.
- Amounts are exact positive integers1..10^12 minor units, not bools/floats. Currency is three uppercase ASCII letters. USD/EUR/GBP are the supported v0.1 model; an unsupported invoice currency is a retained unresolved case, not a guessed conversion. No FX, signed/debit amounts or split-payment aggregation.
- Dates are null or real ISO `YYYY-MM-DD` calendar dates. References/party keys are null or NFC-normalized, trimmed nonempty strings of at most128characters, with no control characters. They remain case-sensitive; no fuzzy company/reference equivalence. Invoice raw reference/date/party are unverified observations and are not silently promoted to confirmed answers.
- Each alternative means its selected records describe ONE payment for this invoice. More than one record asserts a duplicate representation of that payment. Every selected record must have the invoice amount and currency for the alternative to be financially feasible. Invalid financial alternatives remain inspectable with rejection reasons; unknown bank IDs/type/shape violations refuse import without mutation.
- Initial feasible candidates are all financially feasible supplied alternatives, not all imaginable interpretations. `confirmed` is optional and contains any subset of the four clarification fields below, typed and non-null; it filters feasible candidates with the same exact predicate as an operator answer. If none survive, unresolved. Supplied input/original bytes/hash are retained. The planner never receives a hidden truth/expected outcome.

## Predicted observable fields

For each alternative compute, rather than accept an arbitrary answer partition:

| Field | Type | Prediction |
| --- | --- | --- |
| reference | string | Common non-null bank reference of every selected record; otherwise unavailable. |
| date | ISO date | Common non-null booked_on of every selected record; otherwise unavailable. |
| party | string | Common non-null bank party_key of every selected record; otherwise unavailable. |
| duplicate | boolean | More than one selected bank record. The question concerns duplicate representation of the matching payment, not unrelated records elsewhere. |

Operator questions request authoritative clarification, for example from an original payment confirmation; extracted observations are not authenticated proof. A missing prediction is never an invented answer bucket.

## Fixed question menu, costs and ties

Menu order is frozen and is also the fixed baseline order:

1. `reference`: Payment reference — fields[reference], weight1.
2. `date`: Settlement date — fields[date], weight1.
3. `party`: Counterparty key — fields[party], weight2.
4. `duplicate`: Duplicate bank records — fields[duplicate], weight3.
5. `reference_date`: Reference and date — fields[reference,date].
6. `packet`: Confirmation fields — fields[reference,date,party,duplicate].

Field weights are reference1/date1/party2/duplicate3. These are declared effort units, not money or measured customer time. Default lambda1; preregistered sensitivity settings0 and4. Session config is immutable: lambda0..4 integer, question budget0..4/default4, unique field budget0..4/default4. New configuration requires a new session.

At each step take current survivor set S. A field is usable when it is not already known, not previously answered unknown, and every candidate in S has a non-null prediction. A menu item requests its fields intersected with usable fields, in the declared field order. Exclude used menu IDs, empty requests and zero-gain partitions. Thus a compound template never asks a known/unknown field again; it may request only its remaining usable fields. Equal tuple values form disjoint answer buckets. Each requested field is charged once because it becomes known or unavailable after its answer.

For n=|S| and bucket sizes b:

```text
expected_remaining = sum(b*b)/n
expected_eliminated = n - expected_remaining
incremental_cost = 1 + lambda * sum(weight[field] for requested fields)
score = expected_eliminated / incremental_cost
```

Use exact rational/integer comparison, not floating point. Select maximum score, then greater expected elimination, then lower cost, then fewer requested fields, then earlier frozen menu order. No calibrated probabilities, globally optimal decision-tree or guaranteed minimum-question claim. Show requested fields, partitions, expected values, cost and reason. A whole packet is an explicit higher-field option, not a silently preferred default.

Feasibility applies the same remaining question and unique-field budgets to adaptive, fixed and random policies. Keep an unbudgeted feasible list to distinguish no useful question from a budget refusal. The planner is blind to all future answers and truth.

## Requests, answers, persistence and states

- Suggesting is read-only. Requesting explicitly creates one pending request, binds session revision/survivors/question/fields/score/cost and charges one question plus the requested fields/cost. Do not issue another pending request.
- An answer contains exactly the pending requested field keys. Each value has its field type, or null meaning the operator cannot provide it. Non-null values become known; null fields become unavailable for the rest of this session. Recompute survivors from the original financially feasible set and every known field; null eliminates nothing. Never choose a nearest match.
- Invalid type/keys, wrong request ID or stale revision are refused without any state/cost change. Exact replay of an already committed answer returns the retained receipt without a second charge. A different answer for that same request is a conflict. No answer editing in-place; explicit new session from original input is recovery and preserves the old journal.
- SQLite-local transactions serialize changes, with revision checks for concurrent UI/CLI writers. Keep original input, immutable request/answer receipts and source/hash provenance. UTC audit timestamps do not determine eligibility. One planner implementation serves CLI and loopback UI; no second browser arbiter.
- State priority: unsupported invoice currency → unresolved/unsupported_currency; pending request → awaiting_answer;0 survivors → unresolved/inconsistent_observations (or no_feasible_alternatives before any observations);1 survivor → resolved_within_model; otherwise if useful unbudgeted questions exist but budgets prevent them → unresolved/budget_exhausted; otherwise no useful question → unresolved/indistinguishable; else active with a suggestion.
- Resolution is conditional on supplied alternatives/assumptions. An unseen truth that mimics a supplied candidate cannot universally be detected. This limitation must be stated; detectable unsupported inputs, contradictory answers and ambiguity must fail closed. No financial approval, document authentication or real bank write.

## Required executable acceptance

Import arbitrary conforming case bytes → inspect ranked suggestion/partitions → explicitly request fields → submit typed answer → observe actual survivor transition → reopen another process on same DB → export journal. Fresh non-benchmark input must work; never dispatch by named fixture ID. Representative failure: unmodelled reference creates no survivor and remains unresolved; a new session from unchanged original input can accept a corrected reference, without deleting the failed journal. Include stale request, exact replay, unknown answer, budget and malformed input checks. No paid credentials required and no model integration is advertised.

UI: a compact case/source view, surviving alternatives, next request with fields/partition/cost, typed answer controls, status/reason and journal. Every visible element supports input, decision, state or evidence. Native minimal strand SVG and restrained cool glass surfaces; no slogans, promotional hero or arbitrary counters. Read-only recorded example must be labelled; local UI operates the actual engine.

## Evaluation contract before any corpus outputs

- Separate curator authors at least30 development cases D01–D30 and10 held-out H01–H10 with known correct supported alternatives. Most have2–8 initial feasible alternatives and varied partitions, duplicates, missing predictions/unknown answers, confirmed fields and budgets; not just string-renamed copies. Include expected resolved/unresolved outcomes and explicit oracle answers, which are kept OUTSIDE planner inputs. Add a separate8-case unsupported/contradiction/invalid-input stress set, separate denominator.
- Seal exact input/oracle bytes, IDs, split, expected statuses and question/config contract before execution. Curator must not read implementation or product outputs while authoring. Root may inspect D after sealing. H inputs/oracles remain uninspected by implementer until core/config/evaluator freeze; a separate evaluator executes first H. Preserve first failures. Any fixes prompted by H make subsequent H a regression, requiring fresh held-out data for a new held-out claim.
- Compare adaptive defaultlambda1, fixed menu order and uniform random among the SAME currently feasible menu IDs. All skip empty/zero-gain/already-used questions and obey identical unknown, budget and stop rules. Random seeds0–19, seed each case with the big-endian first8bytes of SHA256(`split + ':' + case_id + ':' + seed`), then Python random.Random(seed_value).choice in frozen menu order. Record Python/RNG version;20seeds are repeats, not20times more independent cases.
- Evaluate sensitivitylambda0 and4 separately, not post-hoc best choice. For fixed/random, use each same lambda/config when comparing costs. Report each split/config/policy, all-case and conditional-on-correct-resolution median/p90 question counts, resolved/unresolved counts/rates, wrong resolutions, unique requested fields, total field-request events and declared cost. Unknown answers and refused budget cases remain in effort denominators. Never hide unresolved cases behind a lower conditional median.
- Gold IDs/answers only exist in the evaluator/oracle process. The planner worker receives case input, config and the answer to its already selected request, never truth IDs or future answers. A wrong singleton counts wrong; the evaluator must not use gold to veto a bad resolution or grant a new try. No customer savings or general model-accuracy claim follows.
- Small workload timing must state machine/version/source/config and distinguish actual wall time from abstract field-cost units. Both actual independent source and clean acceptance reviews must cover final source/artifacts and advertised behavior before public release.

## Pre-corpus clarifications adopted from consistency review

1. All keys shown in the case example are required except title and confirmed. Nullable keys are present with explicit null. Format is integer1, not boolean. Reject controls/formats/surrogates and line/paragraph separators in supplied field strings, then normalize NFC/trim before length and equality checks; preserve original raw bytes. Accept any bank_ids order and sort canonically. Invoice.id and bank event IDs share one document namespace; alternative IDs use a separate namespace.
2. Initial confirmed values are permitted only when EVERY financially feasible alternative has a non-null prediction for that field. Otherwise refuse that confirmed input without mutation, explaining that the supplied alternatives cannot all be checked against that observation. After validation, survival means exact equality for every known field. This strict rule avoids discarding an unknown prediction as if it were an observed mismatch. Null answers never enter known and eliminate nothing. No extra missing-evidence singleton state is required.
3. New session revision0. Each committed request and first committed answer increments once; reads/replays do not. A pending request records its pre-request basis revision and exposes the resulting session revision for answering. For an already committed answer in the same session/request, validate/canonicalize the typed answer payload and compare with its receipt BEFORE checking current revision: identical mapping returns retained receipt/current view without mutation; different mapping is conflict. Only a first answer must match current revision and pending request. Request creation itself is not automatically retried or replayed.
4. For n>1, define U as useful questions without budgets and B as its budget-feasible subset. B nonempty =>active; U nonempty/B empty =>budget_exhausted; U empty =>indistinguishable. An empty original financial set gives no_feasible_alternatives; a nonempty set filtered to zero gives inconsistent_observations. Unsupported/pending/singleton priorities remain as stated. A packet exceeding the budget does not prevent a smaller feasible question.
5. Oracle is ONE immutable value/null per primitive field, independent of policy/menuID/seed. Return only pending fields from that same oracle. Supported D/H gold is financially feasible, survives initial confirmed values, and each non-null oracle value agrees with the gold prediction; deliberate contradictions belong to stress. A per-case expected terminal status must be labelled policy/config/seed or an invariant valid for every run; different policies can legitimately have different unresolved rates. No requirement to precompute all random trajectories.
6. Seed text is UTF-8, split literal D/H/S, exact caseID and decimal seed0–19 separated by colons. Run settings/budgets are non-secret input configuration, separate from truth/oracle fields; sensitivity overrides only lambda. Median is the ordinary midpoint median; p90 is nearest rank ceil(0.9*n),1-based. Empty conditional denominator gives null metrics plus denominator0. Random summaries retain per-seed metrics and variation; pooled case×seed rows are explicitly repeated runs, not independent cases.

This v1 is the complete preregistered contract. Any later change must be a new version with rationale and chronology; never rewrite sealed labels after observing product outputs.
