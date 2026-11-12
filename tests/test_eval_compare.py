import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evals.compare_evals import compare_reports


class CompareEvalsTests(unittest.TestCase):
    def write_report(self, folder, name, model, score):
        path = Path(folder) / name
        path.write_text(
            '{"config":{"dataset":"core","judge_provider":"ollama","judge_model":"judge",'
            f'"provider":"{model}","model":"{model}"}},'
            f'"cases":[{{"id":"E1","grade":{{"score":{score}}}}}]}}',
            encoding='utf-8',
        )
        return str(path)

    def test_compares_matching_reports(self):
        with tempfile.TemporaryDirectory() as folder:
            baseline = self.write_report(folder, 'before.json', 'local', 60)
            candidate = self.write_report(folder, 'after.json', 'api', 75)
            _, _, rows = compare_reports(baseline, candidate)
        self.assertEqual(rows, [('E1', 60, 75, 15)])

    def test_rejects_different_judges(self):
        with tempfile.TemporaryDirectory() as folder:
            baseline = self.write_report(folder, 'before.json', 'local', 60)
            candidate = self.write_report(folder, 'after.json', 'api', 75)
            Path(candidate).write_text(
                Path(candidate).read_text(encoding='utf-8').replace('"judge_model":"judge"', '"judge_model":"other"'),
                encoding='utf-8',
            )
            with self.assertRaisesRegex(ValueError, 'judge_model'):
                compare_reports(baseline, candidate)


if __name__ == '__main__':
    unittest.main()
