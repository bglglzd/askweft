from concurrent.futures import ThreadPoolExecutor
import copy
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from askweft import domain, planner
from askweft.domain import Error, encoded
from askweft.store import Engine

EXAMPLE = Path(__file__).resolve().parents[1] / "askweft/examples/invoice.json"


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(prefix="askweft-test-")
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "state.sqlite"
        self.engine = Engine(self.path)
        self.raw = EXAMPLE.read_bytes()
        self.case = json.loads(self.raw)

    def start(self, case=None, config=None):
        return self.engine.import_case(encoded(case) if case is not None else self.raw,
                                       config)["session"]

    def request(self, session, name="reference"):
        return self.engine.request(session["id"], session["revision"], name)["session"]

    def answer(self, session, values):
        return self.engine.answer(session["id"], session["revision"], session["pending"]["id"],
                                  values)["session"]

    def test_exact_partition_cost_and_financial_rejection(self):
        session = self.start()
        self.assertEqual(session["survivors"], ["single-a", "single-b", "duplicate-b"])
        self.assertEqual(session["suggestion"]["id"], "reference")
        question = session["suggestion"]
        self.assertEqual(planner.fraction(question["expected_remaining"]), Fraction(5, 3))
        self.assertEqual(planner.fraction(question["expected_eliminated"]), Fraction(4, 3))
        self.assertEqual(planner.fraction(question["score"]), Fraction(2, 3))
        self.assertEqual(question["cost"], 2)
        self.assertEqual(session["alternatives"][-1]["rejection_reasons"], ["amount_mismatch"])

    def test_request_answer_reopen_and_original_hash(self):
        session = self.start()
        self.assertEqual(session["input_sha256"], sha256(self.raw).hexdigest())
        pending = self.request(session)
        self.assertEqual(pending["revision"], 1)
        self.assertEqual(pending["pending"]["basis_revision"], 0)
        resolved = self.answer(pending, {"reference": "PAY-41"})
        self.assertEqual(resolved["status"], "resolved_within_model")
        self.assertEqual(resolved["survivors"], ["single-a"])
        reopened = Engine(self.path).state(resolved["id"])["session"]
        self.assertEqual(reopened, resolved)
        self.assertEqual(self.engine.original(session["id"]), self.raw)
        self.assertEqual(resolved["usage"], {"questions": 1, "fields": 1,
                                          "field_names": ["reference"], "cost": 2})

    def test_same_answer_replay_precedes_stale_revision(self):
        pending = self.request(self.start())
        result = self.engine.answer(pending["id"], 1, pending["pending"]["id"], {"reference":"PAY-41"})
        replay = self.engine.answer(pending["id"], 0, pending["pending"]["id"], {"reference":" PAY-41 "})
        self.assertTrue(replay["replayed"])
        self.assertEqual(replay["receipt"], result["receipt"])
        self.assertEqual(replay["session"], result["session"])
        with self.assertRaisesRegex(Error, "different answer"):
            self.engine.answer(pending["id"], 0, pending["pending"]["id"], {"reference":"PAY-42"})
        self.assertEqual(self.engine.state(pending["id"])["session"], result["session"])

    def test_bad_answers_do_not_mutate_and_request_not_replayed(self):
        initial = self.start()
        pending = self.request(initial)
        for answer in ({}, {"reference": True}, {"reference": "X", "date": None}):
            with self.subTest(answer=answer), self.assertRaises(Error):
                self.engine.answer(pending["id"], 1, pending["pending"]["id"], answer)
            self.assertEqual(self.engine.state(pending["id"])["session"], pending)
        with self.assertRaises(Error):
            self.engine.answer(pending["id"], 0, pending["pending"]["id"], {"reference":"PAY-41"})
        with self.assertRaises(Error):
            self.request(initial)
        self.assertEqual(self.engine.state(pending["id"])["session"], pending)

    def test_unknown_eliminates_nothing_and_never_reasks(self):
        pending = self.request(self.start())
        session = self.answer(pending, {"reference": None})
        self.assertEqual(session["survivors"], ["single-a", "single-b", "duplicate-b"])
        self.assertEqual(session["known"], {})
        self.assertEqual(session["unavailable_fields"], ["reference"])
        self.assertTrue(all("reference" not in q["fields"] for q in session["options"]))
        self.assertEqual(session["suggestion"]["id"], "date")

    def test_contradiction_and_new_session_recovery_preserve_old(self):
        pending = self.request(self.start())
        failed = self.answer(pending, {"reference": "OUTSIDE-MODEL"})
        self.assertEqual((failed["status"], failed["reason"]),
                         ("unresolved", "inconsistent_observations"))
        restarted = self.engine.restart(failed["id"])["session"]
        self.assertNotEqual(restarted["id"], failed["id"])
        self.assertEqual(restarted["revision"], 0)
        recovered = self.answer(self.request(restarted), {"reference":"PAY-41"})
        self.assertEqual(recovered["survivors"], ["single-a"])
        self.assertEqual(self.engine.state(failed["id"])["session"], failed)

    def test_budgets_and_priority(self):
        for question_budget, field_budget in ((0, 4), (4, 0)):
            result = self.start(config={"lambda":1, "question_budget":question_budget,
                                        "field_budget":field_budget})
            self.assertEqual(result["reason"], "budget_exhausted")
        result = self.start(config={"lambda":1, "question_budget":1, "field_budget":1})
        self.assertTrue(result["options"])
        self.assertTrue(all(len(item["fields"]) == 1 for item in result["options"]))
        unsupported = copy.deepcopy(self.case)
        unsupported["invoice"]["currency"] = "JPY"
        result = self.start(unsupported)
        self.assertEqual(result["reason"], "unsupported_currency")

    def test_missing_predictions_are_not_false_mismatches(self):
        case = copy.deepcopy(self.case)
        case["bank_events"][0]["reference"] = None
        session = self.start(case)
        self.assertTrue(all("reference" not in q["fields"] for q in session["options"]))
        case["confirmed"] = {"reference":"PAY-42"}
        before = self.engine.state()
        with self.assertRaisesRegex(Error, "no prediction"):
            self.start(case)
        self.assertEqual(self.engine.state(), before)

    def test_duplicate_record_groups_are_not_summed(self):
        case = copy.deepcopy(self.case)
        case["bank_events"][1]["amount_minor"] = 9225
        case["bank_events"][2]["amount_minor"] = 9225
        session = self.start(case)
        duplicate = next(item for item in session["alternatives"] if item["id"] == "duplicate-b")
        self.assertFalse(duplicate["feasible"])
        self.assertEqual(duplicate["predictions"]["duplicate"], True)

    def test_invalid_boundaries_without_mutation(self):
        self.start()
        before = self.engine.state()
        bad = []
        for path, value in ((["format"], True), (["invoice","amount_minor"], 1.0),
                            (["invoice","issued_on"], "2031-02-29"),
                            (["invoice","reference"], "\u202eX"), (["invoice","currency"], "usd"),
                            (["invoice","id"], "BANK-A")):
            case = copy.deepcopy(self.case)
            target = case
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = value
            bad.append(encoded(case))
        bad += [b'{"format":1,"format":1}', b'{"amount":NaN}', b'{', b'[]',
                b" " * (domain.MAX_INPUT + 1)]
        for raw in bad:
            with self.subTest(raw=raw[:40]), self.assertRaises(Error):
                self.engine.import_case(raw)
            self.assertEqual(self.engine.state(), before)

    def test_concurrent_requests_charge_once(self):
        session = self.start()

        def request(_):
            try:
                return Engine(self.path).request(session["id"], 0, "reference")
            except Error as error:
                return error.code

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(request, range(2)))
        self.assertEqual(sum(isinstance(result, dict) for result in results), 1)
        self.assertIn("stale_revision", results)
        self.assertEqual(self.engine.state(session["id"])["session"]["usage"]["questions"], 1)

    def test_empty_financial_set_and_indistinguishable(self):
        case = copy.deepcopy(self.case)
        case["alternatives"] = []
        self.assertEqual(self.start(case)["reason"], "no_feasible_alternatives")
        case = copy.deepcopy(self.case)
        for event in case["bank_events"]:
            event.update(reference="SAME", booked_on="2030-06-03", party_key="harbor")
        case["alternatives"] = case["alternatives"][:2]
        self.assertEqual(self.start(case)["reason"], "indistinguishable")


if __name__ == "__main__":
    unittest.main()
