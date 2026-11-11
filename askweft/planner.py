"""One exact-rational planner shared by CLI, HTTP and evaluation workers."""

from fractions import Fraction

from .domain import FIELDS, SUPPORTED, derive

WEIGHTS = {"reference": 1, "date": 1, "party": 2, "duplicate": 3}
MENU = (
    ("reference", "Payment reference", ("reference",)),
    ("date", "Settlement date", ("date",)),
    ("party", "Counterparty key", ("party",)),
    ("duplicate", "Duplicate bank records", ("duplicate",)),
    ("reference_date", "Reference and date", ("reference", "date")),
    ("packet", "Confirmation fields", FIELDS),
)


def rational(value):
    return {"numerator": value.numerator, "denominator": value.denominator}


def fraction(value):
    return Fraction(value["numerator"], value["denominator"])


def analyze(case, config, known, unavailable, used, usage, pending=None):
    alternatives = derive(case)
    for item in alternatives:
        item["survives"] = item["feasible"] and all(
            item["predictions"][field] == value for field, value in known.items()
        )
    survivors = [item for item in alternatives if item["survives"]]
    usable = [
        field
        for field in FIELDS
        if field not in known
        and field not in unavailable
        and all(item["predictions"][field] is not None for item in survivors)
    ]
    unbudgeted, options = [], []
    if len(survivors) > 1:
        n = len(survivors)
        for order, (name, title, menu_fields) in enumerate(MENU):
            fields = [field for field in menu_fields if field in usable]
            if name in used or not fields:
                continue
            partitions = {}
            for item in survivors:
                key = tuple(item["predictions"][field] for field in fields)
                partitions.setdefault(key, []).append(item["id"])
            if len(partitions) < 2:
                continue
            remaining = Fraction(sum(len(bucket) ** 2 for bucket in partitions.values()), n)
            eliminated = n - remaining
            cost = 1 + config["lambda"] * sum(WEIGHTS[field] for field in fields)
            question = {
                "id": name,
                "title": title,
                "fields": fields,
                "cost": cost,
                "expected_remaining": rational(remaining),
                "expected_eliminated": rational(eliminated),
                "score": rational(eliminated / cost),
                "partitions": [
                    {"values": dict(zip(fields, key)), "alternatives": bucket}
                    for key, bucket in partitions.items()
                ],
            }
            # Order is private comparison metadata; the public representation stays inspectable.
            rank = (-eliminated / cost, -eliminated, cost, len(fields), order)
            unbudgeted.append((rank, question))
            if (
                usage["questions"] < config["question_budget"]
                and usage["fields"] + len(fields) <= config["field_budget"]
            ):
                options.append((rank, question))
    options.sort(key=lambda pair: pair[0])
    if case["invoice"]["currency"] not in SUPPORTED:
        status, reason = "unresolved", "unsupported_currency"
    elif pending:
        status, reason = "awaiting_answer", "answer_required"
    elif not survivors:
        status = "unresolved"
        reason = (
            "inconsistent_observations"
            if any(item["feasible"] for item in alternatives)
            else "no_feasible_alternatives"
        )
    elif len(survivors) == 1:
        status, reason = "resolved_within_model", "one_supplied_alternative"
    elif not options:
        status = "unresolved"
        reason = "budget_exhausted" if unbudgeted else "indistinguishable"
    else:
        status, reason = "active", "useful_request_available"
    visible = [question for _, question in options] if status == "active" else []
    return {
        "alternatives": alternatives,
        "survivors": [item["id"] for item in survivors],
        "status": status,
        "reason": reason,
        "options": visible,
        "suggestion": visible[0] if visible else None,
    }
