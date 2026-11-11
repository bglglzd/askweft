# Case and request contract

An operations specialist supplies one extracted invoice, bank events and explicit candidate
record groups. Askweft checks financial compatibility, shows the surviving alternatives and
ranks field requests. A request is explicit and charged; an answer narrows the alternatives.
The SQLite journal survives process restart. Export includes the actual state and provenance.

One remaining candidate is `resolved_within_model`. This result depends on the supplied
interpretations; an unseen interpretation can mimic an included one. No financial action,
document authentication or approval follows. Unknown evidence, budget exhaustion and
indistinguishable candidates remain unresolved. An answer outside the model yields
`inconsistent_observations`; restarting creates a new session from the original bytes and
preserves the failed journal.

## Input

The [synthetic example](../askweft/examples/invoice.json) is native Case v1 JSON, not a lookup
key. All its keys are required except `title` and `confirmed`. Nullable fields must be
present with explicit null. Duplicate JSON keys, nonfinite numbers and unknown keys are
refused. Maximum UTF-8 input size: 256 KiB.

- One invoice, 0–16 bank events, 0–16 alternatives. Each alternative selects 1–4 distinct
  existing bank IDs. Selected IDs are sorted; duplicate selected-record sets are refused.
- IDs match `[A-Za-z0-9][A-Za-z0-9_.-]{0,63}`. Invoice and bank IDs share one unique namespace;
  alternative IDs have a separate namespace.
- Amounts are positive integer minor units, 1 through 1,000,000,000,000. Floats and booleans
  are refused. Currency is three uppercase ASCII letters; invoice USD/EUR/GBP are supported.
  Other invoice currencies are retained as unresolved `unsupported_currency`.
- Dates are real ISO `YYYY-MM-DD` dates or null. References and party keys are null or
  NFC-normalized, trimmed nonempty text, at most 128 characters. Controls, format characters,
  surrogates and line/paragraph separators are refused. Equality is case-sensitive. Title is
  optional presentation text, at most 120 characters.
- A group represents **one payment**. Multiple records assert duplicate representation,
  never a split-payment sum. Every selected record must have the invoice amount/currency.
  Financial mismatches remain inspectable; structural errors refuse the import.

Each group predicts a reference, booked date and party key only if all its selected records
agree on a non-null value. `duplicate` is true for groups with more than one record. Invoice
reference/date/party are unverified observations, not automatic answers. Initial `confirmed`
is a typed, non-null subset of reference/date/party/duplicate; every financially feasible
alternative must predict a non-null value for each confirmed field, otherwise import is
refused. All known fields then filter by exact equality. Original input bytes/hash are kept.

## Selection

Menu order: `reference`, `date`, `party`, `duplicate`, `reference_date` (reference/date),
`packet` (all four). Field weights: 1, 1, 2, 3. Immutable config: integer `lambda` 0–4
(default 1), question budget 0–4 (default 4), unique field budget 0–4 (default 4).

A field is usable if it is neither known nor previously answered unknown, and every current
survivor predicts it. A menu requests its usable fields only. Used menu IDs, empty requests
and zero-gain partitions are excluded. Projected aliases remain separate menu IDs.

For equally weighted survivors and answer buckets of size b:

```text
expected_remaining = sum(b*b) / number_of_survivors
expected_eliminated = number_of_survivors - expected_remaining
cost = 1 + lambda * sum(requested_field_weights)
score = expected_eliminated / cost
```

Use exact rational arithmetic. Ties prefer greater elimination, lower cost, fewer fields,
then earlier menu order. These are declared effort units, not time or money. No probability
calibration, optimal decision-tree or minimum-question guarantee is claimed.

## Transactions and stopping

Read/suggest changes nothing. A request creates one pending request, records its basis
revision/survivors/partitions and charges a question/fields/cost. An answer has exactly the
pending fields, typed values or explicit null. Null eliminates nothing and makes that field
unavailable for the session. Known values filter the original financial candidate set.

Revision starts at zero and increments once for each request/first answer. Invalid input,
stale revision and conflicting replay do not change state. An identical canonical answer
replay is checked **before** current revision and returns its retained receipt without a
second charge. Requests are not automatically replayed. Corrections/config changes need a
new session; old journals remain.

Stopping priority: unsupported currency; pending answer; no survivors (no financial
candidates versus contradictory observations); one supplied survivor; useful budget-feasible
question; budget exhaustion when useful unbudgeted questions remain; otherwise
indistinguishable. A larger packet exceeding budget never blocks a smaller feasible request.

## Acceptance

Arbitrary fresh case import → inspect exact partitions → request → typed answer → actual
survivor transition → reopen from another process → export. Check contradictions/restart,
unknowns, exhausted budgets, financial rejection, malformed input, revision races and replay.
Compare adaptive/fixed/random on separately authored synthetic cases with identical answers,
budgets and stop rules; disclose unresolved/wrong outcomes alongside effort.
