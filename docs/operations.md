# Local operation and recovery

Install with Python 3.11 or newer as shown in the README. `askweft --version` prints the
package version. The package has no runtime dependencies and does not contact a model or bank.

## Browser

```console
askweft --db example.sqlite demo
```

Open the printed numeric loopback URL. A synthetic case is seeded only if this database has
no sessions; existing data is preserved. Use `--db another.sqlite` for a fresh workspace.
`askweft --db work.sqlite serve` starts an empty or existing operator workspace without seeding.
`--port 0` asks the OS for a free port. Ctrl+C stops the server; it does not delete the journal.

In the synthetic case, request **Payment reference**, answer `PAY-42`, then request
**Duplicate bank records** and choose Yes. `duplicate-b` remains. Restart the session and answer
the reference with `OUTSIDE-MODEL`: no candidate matches, and the case stays unresolved.
Restart once more to enter a corrected answer; the failed session remains available.

Import a Case v1 file through **Import case**, or paste raw JSON. File text is retained until
edited; the server validates duplicate keys and types. Previewing another question changes
no state. **Request these fields** charges its shown question/field/cost burden. The answer
form starts blank. Choose Unknown explicitly when the field cannot be supplied; it eliminates
nothing and cannot be requested again in that session.

The hosted example is a labelled read-only recording. Its saved stages are actual engine
outputs; it does not run Python or accept imports/answers. A local workspace going offline
keeps its last received view and disables writes. It never switches to a recording. If the
server restarts, refresh connection/state and explicitly retry an intended action. Writes
are never automatically replayed by the browser. **Export state** downloads the received
session, alternatives and journal; the CLI can also export exact original source bytes.

## CLI

```console
askweft --db work.sqlite import case.json
askweft --db work.sqlite state
askweft --db work.sqlite suggest
```

Import prints a full JSON view including session ID, revision, suggestion and partitions.
Replace the uppercase placeholders below with the actual printed IDs/revision. Create an
answer JSON file containing exactly the pending fields, for example `{"reference":"PAY-42"}`.

```console
askweft --db work.sqlite request --session SESSION_ID --revision 0 --question reference
askweft --db work.sqlite answer --session SESSION_ID --revision 1 --request REQUEST_ID --answer-file answer.json
askweft --db work.sqlite export --session SESSION_ID
askweft --db work.sqlite export --session SESSION_ID --original
askweft --db work.sqlite restart --session SESSION_ID
```

`--answer-file -` reads a typed mapping from standard input. Import accepts `-` too. Requests
and answers print the current full view; answers also return their receipt and replay flag.
An identical canonical answer replay returns the same receipt even with an old revision.
A different answer for that request is a conflict. Restart preserves original bytes and
the prior journal. It does not copy prior answers.

Import/restart accept `--lambda 0..4`, `--question-budget 0..4` and `--field-budget 0..4`.
Defaults are 1, 4 and 4. Configuration is immutable within a session. A zero budget can
leave an ambiguous case unresolved immediately. Declared cost units are neither money nor
measured operator time.

`askweft record recorded.json` writes six synthetic engine stages to a **new** file and
refuses to overwrite an existing one. `state`, `suggest` and `export` are read-only.
CLI input/store failures use exit code 2 and a concise error; successful commands use 0.

## Boundaries and troubleshooting

- `invalid_input`: fix the reported shape/type/date/ID issue. A rejected import/answer does
  not change an existing session. Explicit blank session IDs are refused.
- `stale_revision`: read state and review the current pending request before retrying.
- `answer_conflict`: the request already has another answer. Start a new session to correct it.
- `inconsistent_observations`: supplied alternatives cannot explain the recorded known values.
  Inspect the source/model and restart with appropriate input; there is no nearest-match fallback.
- `budget_exhausted` or `indistinguishable`: inspect remaining alternatives; changing limits
  requires a new session. Unknown evidence is retained, not guessed.
- `store_unavailable`: check the path, permissions, disk and competing writer. Preserve the
  original database before attempting recovery. Use a fresh path for another workspace.
- `host_refused` / `origin_refused`: open the exact numeric loopback URL, rather than a proxy,
  remote host or alternate hostname. The service is a local operator tool, not multi-user auth.

Stop all users of a database before copying it for a simple offline backup. Keep source and
SQLite files private when they contain your own records. No telemetry or automatic external
financial action is implemented.
