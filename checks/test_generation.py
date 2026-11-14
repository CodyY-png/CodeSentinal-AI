"""Offline checks of API response handling. Never call a live service."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from generate_tests import call_api, discover_modules, extract_code
from urllib.error import HTTPError


def response(text):
    return {'status': 'completed', 'output': [
        {'type': 'reasoning'},
        {'type': 'message', 'content': [{'type': 'output_text', 'text': text}]},
    ]}


class GenerationChecks(unittest.TestCase):
    def test_discovers_nested_sources_without_reading_test_or_environment_files(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            for relative in ('main.py', 'src/example/service.py', 'tests/test_service.py',
                             '.venv/dependency.py', 'generated/candidate.py'):
                path = project / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('value = 1\n', encoding='utf-8')
            modules, skipped = discover_modules(project)
        self.assertEqual([path for path, _ in modules], ['main.py', 'src/example/service.py'])
        self.assertEqual(skipped, [])

    def test_extracts_code_after_reasoning_item(self):
        code = 'def test_zero():\n    assert 0 == 0'
        self.assertEqual(extract_code(response(code)), code + '\n')

    def test_rejects_truncated_response(self):
        with self.assertRaises(ValueError):
            extract_code({'status': 'incomplete', 'output': []})

    def test_rejects_refusal(self):
        with self.assertRaises(ValueError):
            extract_code({'status': 'completed', 'output': [
                {'type': 'message', 'content': [{'type': 'refusal'}]}]})

    def test_rejects_invalid_python_and_missing_tests(self):
        for code in ['def test_bad(:', 'print("no tests")', '']:
            with self.subTest(code=code), self.assertRaises((ValueError, SyntaxError)):
                extract_code(response(code))

    @patch('generate_tests.request.urlopen')
    def test_http_error_does_not_expose_body_or_key(self, mocked):
        mocked.side_effect = HTTPError('https://api.openai.com/v1/responses', 401, 'secret-body', {}, None)
        with self.assertRaises(RuntimeError) as caught:
            call_api({'model': 'offline'}, 'fake-key')
        self.assertNotIn('fake-key', str(caught.exception))
        self.assertNotIn('secret-body', str(caught.exception))


if __name__ == '__main__':
    unittest.main()
