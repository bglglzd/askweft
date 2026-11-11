"""Strict input boundaries and predictions derived from selected bank records."""

from datetime import date
import json
import re
import unicodedata

MAX_INPUT = 256 * 1024
FIELDS = ("reference", "date", "party", "duplicate")
SUPPORTED = ("USD", "EUR", "GBP")
ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z", re.ASCII)


class Error(Exception):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def require(condition, message, code="invalid_input"):
    if not condition:
        raise Error(code, message)


def keys(value, required, optional=()):
    require(type(value) is dict, "Expected a JSON object")
    require(set(required) <= value.keys() <= set(required) | set(optional),
            "Missing or unknown object keys")


def encoded(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")


def loads(raw, limit=MAX_INPUT):
    if type(raw) is str:
        try:
            raw = raw.encode("utf-8")
        except UnicodeError as error:
            raise Error("invalid_input", "Input must contain valid UTF-8") from error
    require(type(raw) is bytes, "Input must be UTF-8 JSON bytes")
    require(len(raw) <= limit, "JSON input exceeds the size limit", "too_large")

    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, f"Duplicate JSON key: {key!r}")
            result[key] = value
        return result

    def constant(_):
        raise Error("invalid_input", "Nonfinite JSON numbers are not supported")

    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant)
    except (UnicodeError, ValueError, RecursionError) as error:
        raise Error("invalid_input", "Malformed UTF-8 JSON") from error


def identifier(value):
    require(type(value) is str and ID.fullmatch(value) is not None, "Invalid identifier")
    return value


def text(value, maximum=128):
    require(type(value) is str, "Expected text")
    require(not any(unicodedata.category(char) in ("Cc", "Cf", "Cs", "Zl", "Zp")
                    for char in value), "Control, format and surrogate characters are refused")
    value = unicodedata.normalize("NFC", value).strip()
    require(0 < len(value) <= maximum, f"Text must contain 1..{maximum} characters")
    return value


def calendar(value):
    require(type(value) is str and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value),
            "Expected an ISO YYYY-MM-DD calendar date")
    try:
        require(date.fromisoformat(value).isoformat() == value, "Invalid calendar date")
    except ValueError as error:
        raise Error("invalid_input", "Invalid calendar date") from error
    return value


def field_value(field, value, *, nullable=True):
    require(field in FIELDS, "Unknown clarification field")
    if value is None and nullable:
        return None
    if field == "duplicate":
        require(type(value) is bool, "Duplicate must be a boolean or explicit null")
        return value
    return calendar(value) if field == "date" else text(value)


def values(value, fields, *, exact=True, nullable=True):
    keys(value, fields if exact else (), () if exact else fields)
    return {field: field_value(field, value[field], nullable=nullable)
            for field in FIELDS if field in value}


def config(value=None):
    if value is None:
        return {"lambda": 1, "question_budget": 4, "field_budget": 4}
    keys(value, ("lambda", "question_budget", "field_budget"))
    for key, number in value.items():
        require(type(number) is int and 0 <= number <= 4, f"{key} must be an integer in 0..4")
    return dict(value)


def document(value, *, invoice=False):
    when = "issued_on" if invoice else "booked_on"
    keys(value, ("id", "amount_minor", "currency", when, "reference", "party_key"))
    identifier(value["id"])
    require(type(value["amount_minor"]) is int and 1 <= value["amount_minor"] <= 10**12,
            "amount_minor must be a positive integer in 1..1000000000000")
    require(type(value["currency"]) is str
            and re.fullmatch(r"[A-Z]{3}", value["currency"], re.ASCII),
            "Currency must be three uppercase ASCII letters")
    result = dict(value)
    result[when] = None if value[when] is None else calendar(value[when])
    for field in ("reference", "party_key"):
        result[field] = None if value[field] is None else text(value[field])
    return result


def predictions(records):
    result = {}
    for field, source in (("reference", "reference"), ("date", "booked_on"),
                          ("party", "party_key")):
        observed = [record[source] for record in records]
        result[field] = observed[0] if observed[0] is not None and len(set(observed)) == 1 else None
    result["duplicate"] = len(records) > 1
    return result


def derive(case):
    invoice = case["invoice"]
    banks = {record["id"]: record for record in case["bank_events"]}
    result = []
    for alternative in case["alternatives"]:
        records = [banks[record_id] for record_id in alternative["bank_ids"]]
        reasons = []
        if any(record["amount_minor"] != invoice["amount_minor"] for record in records):
            reasons.append("amount_mismatch")
        if any(record["currency"] != invoice["currency"] for record in records):
            reasons.append("currency_mismatch")
        result.append({**alternative, "feasible": not reasons,
                       "rejection_reasons": reasons, "predictions": predictions(records)})
    return result


def parse_case(raw):
    case = loads(raw)
    keys(case, ("format", "id", "invoice", "bank_events", "alternatives"), ("title", "confirmed"))
    require(type(case["format"]) is int and case["format"] == 1, "Expected format integer 1")
    identifier(case["id"])
    result = {"format": 1, "id": case["id"], "invoice": document(case["invoice"], invoice=True)}
    if "title" in case:
        result["title"] = text(case["title"], 120)
    for collection in ("bank_events", "alternatives"):
        require(type(case[collection]) is list and len(case[collection]) <= 16,
                f"{collection} must contain 0..16 items")
    result["bank_events"] = [document(value) for value in case["bank_events"]]
    ids = [result["invoice"]["id"]] + [record["id"] for record in result["bank_events"]]
    require(len(set(ids)) == len(ids), "Invoice and bank document IDs must be unique")
    bank_ids = set(ids[1:])
    alternatives, names, groups = [], set(), set()
    for alternative in case["alternatives"]:
        keys(alternative, ("id", "bank_ids"))
        name = identifier(alternative["id"])
        require(name not in names, "Alternative IDs must be unique")
        group = alternative["bank_ids"]
        require(type(group) is list and 1 <= len(group) <= 4, "Select 1..4 distinct bank IDs")
        group = tuple(sorted(identifier(value) for value in group))
        require(len(set(group)) == len(group) and set(group) <= bank_ids,
                "Selected bank IDs must be distinct and exist")
        require(group not in groups, "Duplicate selected-record sets are refused")
        groups.add(group)
        names.add(name)
        alternatives.append({"id": name, "bank_ids": list(group)})
    result["alternatives"] = alternatives
    confirmed = values(case.get("confirmed", {}), FIELDS, exact=False, nullable=False)
    feasible = [alternative for alternative in derive(result) if alternative["feasible"]]
    for field in confirmed:
        require(all(item["predictions"][field] is not None for item in feasible),
                f"Cannot confirm {field}: a feasible alternative has no prediction")
    result["confirmed"] = confirmed
    return result
