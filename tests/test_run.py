import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import run


class RunOutputTests(unittest.TestCase):
    def test_output_file_contains_config_and_result(self):
        result = {'status': 'completed', 'answer': 'ok', 'trace': [], 'usage': []}
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'run.json'
            argv = [
                'run.py', 'check status', '--provider', 'ollama', '--model', 'qwen2.5:3b',
                '--output', str(output),
            ]
            with patch('sys.argv', argv), patch('run.run', return_value=result):
                self.assertEqual(run.main(), 0)

            report = json.loads(output.read_text(encoding='utf-8'))
        self.assertEqual(report['config']['provider'], 'ollama')
        self.assertEqual(report['config']['model'], 'qwen2.5:3b')
        self.assertEqual(report['config']['question'], 'check status')
        self.assertEqual(report['result'], result)
        self.assertTrue(report['created_at'])


if __name__ == '__main__':
    unittest.main()
