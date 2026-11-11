import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from askweft.demo import SCOPE, export_recording, recording

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("prepare_pages", ROOT / "scripts/prepare-pages.py")
PAGES = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PAGES)


class RecordingTests(unittest.TestCase):
    def test_actual_six_transitions_and_closed_recording_shape(self):
        result = recording()
        self.assertEqual(result["scope"], SCOPE)
        sessions = [stage["state"]["session"] for stage in result["stages"]]
        self.assertEqual(
            [session["status"] for session in sessions],
            [
                "active",
                "awaiting_answer",
                "active",
                "awaiting_answer",
                "resolved_within_model",
                "unresolved",
            ],
        )
        self.assertEqual(sessions[4]["survivors"], ["duplicate-b"])
        self.assertEqual(sessions[4]["usage"]["questions"], 2)
        self.assertEqual(sessions[5]["reason"], "inconsistent_observations")
        self.assertNotEqual(sessions[4]["id"], sessions[5]["id"])
        PAGES.recorded_example(result)

    def test_recording_refuses_overwrite(self):
        with TemporaryDirectory(prefix="askweft-record-test-") as temporary:
            target = Path(temporary) / "recorded.json"
            export_recording(target)
            original = target.read_bytes()
            with self.assertRaises(FileExistsError):
                export_recording(target)
            self.assertEqual(target.read_bytes(), original)

    def test_recording_validator_refuses_endpoint_and_wrong_mode(self):
        for mutation in ("endpoint", "mode"):
            result = recording()
            if mutation == "endpoint":
                result["stages"][0]["state"]["endpoint"] = "https://example.invalid"
            else:
                result["stages"][0]["state"]["mode"] = "local"
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                PAGES.recorded_example(result)


if __name__ == "__main__":
    unittest.main()
