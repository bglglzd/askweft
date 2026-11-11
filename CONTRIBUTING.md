# Contributing

Use Python 3.11 or newer. Create a virtual environment, then:

```sh
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
python -m ruff check .
python -m ruff format --check .
node --check askweft/assets/app.js
```

Include a small native input and expected state transition for behavior changes. Preserve
typed unknowns, exact costs, revision guards and answer replay. Explain any change to the
frozen selection/evaluation contract; never rewrite sealed inputs or labels after results.
Use synthetic records in issues and tests. Do not include real financial documents or secrets.

The SQLite file is local operator state. Keep it outside Git. Report security-sensitive
issues through GitHub's private vulnerability reporting when enabled; do not post credentials.
