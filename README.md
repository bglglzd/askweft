# Askweft

Document clarification planning over extracted invoice and bank-event JSON. Askweft shows
competing record groups, ranks field requests by exact expected elimination per declared
cost, records typed answers and preserves unresolved cases in a local SQLite journal.

Python 3.11 or newer; no runtime dependencies.

## Run locally

```sh
git clone https://github.com/bglglzd/askweft.git
cd askweft
python -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/askweft --db example.sqlite demo
```

On Windows use `.venv\Scripts\python.exe` and `.venv\Scripts\askweft.exe`. Open the printed
numeric loopback URL. The synthetic example is seeded only when the database has no sessions.
Ctrl+C stops the server. Use a fresh database path to start again.

Import your own Case v1 JSON through the local UI or `askweft --db work.sqlite import case.json`.
Inspect the candidate partitions, explicitly request a field and provide its actual value
or unknown. An answer outside all candidates stays unresolved. Restarting creates a new
session from retained source bytes and preserves the old answers.

## Scope

One invoice, up to 16 bank events and 16 explicit alternatives. USD/EUR/GBP; integer minor
units; exact, case-sensitive comparisons. A group with multiple records describes duplicate
representation of one payment, never a summed split payment.

One survivor is resolved **within the supplied model**. An unseen truth can mimic an included
candidate. This is not document authentication, financial approval, OCR or a live bank feed.
Question costs are declared units, not measured operator time or money.

[Case/request specification](docs/spec.md) · [Architecture](docs/architecture.md) ·
[Related products and limits](docs/comparison.md) · [MIT license](LICENSE)
