from contextlib import closing
from io import BytesIO
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

from fastapi.testclient import TestClient

from api import create_app


class ApiChecks(unittest.TestCase):
    def test_local_model_generates_without_openai_key(self):
        with patch.dict('os.environ', {'OLLAMA_MODEL': 'local-test', 'OPENAI_API_KEY': ''}):
            with patch('generate_tests.call_ollama') as local, patch('generate_tests.call_api') as cloud:
                output = json.dumps({'findings': [], 'pytest_code': 'def test_example():\n    assert 1 == 1'})
                local.return_value = {'status': 'completed', 'output': [{'type': 'message',
                    'content': [{'type': 'output_text', 'text': output}]}]}
                with TestClient(create_app(self.reports, generated_dir=self.reports / 'generated')) as client:
                    preview = client.post('/generation/previews', json={}).json()
                    self.assertTrue(preview['configured'])
                    self.assertEqual(preview['provider'], 'ollama')
                    url = f"/generation/{preview['id']}/modules/1"
                    payload = client.get(url).json()['request']
                    self.assertEqual(payload['format']['required'], ['findings', 'pytest_code'])
                    self.assertEqual(client.post(url, json={'confirm': True}).status_code, 200)
                local.assert_called_once_with(payload)
                cloud.assert_not_called()

    def setUp(self):
        model_env = patch.dict('os.environ', {'OLLAMA_MODEL': '', 'OPENAI_MODEL': '', 'OPENAI_API_KEY': ''})
        model_env.start()
        self.addCleanup(model_env.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.reports = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_remote_upload_requires_invite_and_separate_report_token(self):
        with patch.dict('os.environ', {'CODESENTINEL_INVITE_PASSWORD': 'test-password-at-least-20'}):
            app = create_app(self.reports, generated_dir=self.reports / 'generated', remote=True)
        data = BytesIO()
        with ZipFile(data, 'w') as archive:
            archive.writestr('example.py', 'value = 1\n')
        with TestClient(app) as client:
            self.assertEqual(client.get('/').status_code, 401)
            self.assertEqual(client.get('/health').status_code, 200)
            client.auth = ('guest', 'test-password-at-least-20')
            self.assertEqual(client.get('/settings').json(), {'remote': True})
            self.assertEqual(client.post('/analyses', json={}).status_code, 404)
            self.assertEqual(client.post('/generation/previews', json={'project': '.'}).status_code, 404)
            uploads = [
                client.post('/generation/uploads', content=data.getvalue(),
                            headers={'Content-Type': 'application/zip'})
                for _ in range(2)
            ]
            self.assertEqual([response.status_code for response in uploads], [200, 200])
            first, second = [response.json() for response in uploads]
            self.assertNotIn('project', first)
            self.assertNotIn('access_digest', first)
            url = f"/generation/{first['id']}/modules/1"
            self.assertEqual(client.get(url).status_code, 404)
            self.assertEqual(client.get(url, headers={'X-Report-Token': second['access_token']}).status_code, 404)
            report = client.get(url, headers={'X-Report-Token': first['access_token']})
            self.assertEqual(report.status_code, 200)
            self.assertEqual(report.headers['Cache-Control'], 'no-store')

    def test_dashboard_project_preview_and_candidate_generation(self):
        project = self.reports / 'example'
        project.mkdir()
        (project / 'calculator.py').write_text('def total():\n    return 3\n', encoding='utf-8')
        (project / 'test_calculator.py').write_text(
            'from calculator import total\n\ndef test_total():\n    assert total() == 3\n', encoding='utf-8')
        with patch.dict('os.environ', {'OPENAI_MODEL': 'offline', 'OPENAI_API_KEY': 'fake-key'}):
            with patch('generate_tests.call_api') as model:
                finding = {'title': '疑似空輸入問題', 'input': '[]', 'expected': '回傳 0',
                           'predicted': '引發例外', 'basis': '推測空輸入應支援',
                           'reproduction': '以空清單呼叫', 'suggestion': '確認空輸入規格'}
                output = json.dumps({'findings': [finding], 'pytest_code': 'def test_total():\n    assert True'})
                model.return_value = {'status': 'completed', 'output': [{'type': 'message',
                    'content': [{'type': 'output_text', 'text': output}]}]}
                with TestClient(create_app(self.reports, generated_dir=self.reports / 'generated')) as client:
                    self.assertEqual(client.get('/').status_code, 200)
                    self.assertEqual(client.get('/static/generation.js').status_code, 200)
                    preview = client.post('/generation/previews', json={'project': str(project)}).json()
                    url = f"/generation/{preview['id']}/modules/1"
                    self.assertEqual(preview['modules'][0]['path'], 'calculator.py')
                    self.assertIsNone(client.get(url).json()['candidate'])
                    self.assertEqual(client.post(url, json={'confirm': False}).status_code, 422)
                    model.assert_not_called()
                    self.assertEqual(client.post(url, json={'confirm': True}).status_code, 200)
                    report = client.get(url).json()
                    self.assertIn('def test_total', report['candidate'])
                    self.assertEqual(report['findings'], [{**finding, 'status': 'unverified'}])
                    model.assert_called_once()
                    task = client.post('/analyses', json={'project': str(project)}).json()
                    result = client.get(task['status_url']).json()
                    self.assertEqual(result['project'], str(project))
                    self.assertEqual(result['result']['counts']['passed'], 1)

    def test_zip_source_preview_and_rejects_path_traversal(self):
        with TestClient(create_app(self.reports, generated_dir=self.reports / 'generated')) as client:
            for name, expected in [('example/service.py', 200), ('../escape.py', 422)]:
                data = BytesIO()
                with ZipFile(data, 'w') as archive:
                    archive.writestr(name, 'def average(items):\n    return sum(items) / len(items)\n')
                result = client.post('/generation/uploads', content=data.getvalue(),
                                     headers={'Content-Type': 'application/zip'})
                self.assertEqual(result.status_code, expected)
                if expected == 200:
                    preview = result.json()
                    module = client.get(f"/generation/{preview['id']}/modules/1").json()
                    self.assertEqual(json.loads(module['request']['input'])['specification'], '')
                    self.assertEqual(preview['modules'][0]['path'], 'service.py')

    def test_real_execution_and_history_survive_restart(self):
        with TestClient(create_app(self.reports)) as client:
            response = client.post('/analyses', json={'timeout': 60})
            self.assertEqual(response.status_code, 202)
            task_id = response.json()['id']
            task = client.get(f'/analyses/{task_id}').json()
            self.assertEqual(task['status'], 'passed')
            self.assertEqual(task['result']['counts']['passed'], 5)
            self.assertTrue((self.reports / task_id / 'summary.json').exists())
        with TestClient(create_app(self.reports)) as client:
            self.assertEqual(client.get('/analyses').json()['items'][0]['id'], task_id)
            self.assertEqual(client.get(f'/analyses/{task_id}').json()['status'], 'passed')

    def test_invalid_timeout_and_unknown_task(self):
        with TestClient(create_app(self.reports)) as client:
            for body in [{'timeout': 0}, {'timeout': 301}, {'timeout': True}, {'command': 'arbitrary'}]:
                self.assertEqual(client.post('/analyses', json=body).status_code, 422)
            self.assertEqual(client.get('/analyses/not-a-task').status_code, 404)

    def test_active_task_conflict_and_restart_recovery(self):
        with TestClient(create_app(self.reports)) as client:
            with closing(sqlite3.connect(self.reports / 'tasks.sqlite3')) as conn:
                with conn:
                    conn.execute("INSERT INTO tasks (id, status, created_at, timeout) VALUES ('stale', 'running', '2026-01-01', 60)")
            self.assertEqual(client.post('/analyses', json={}).status_code, 409)
        with TestClient(create_app(self.reports)) as client:
            self.assertEqual(client.get('/analyses/stale').json()['status'], 'interrupted')

    def test_worker_exception_is_visible(self):
        def broken_runner(**kwargs):
            raise RuntimeError('simulated failure')
        with TestClient(create_app(self.reports, runner=broken_runner)) as client:
            task_id = client.post('/analyses', json={}).json()['id']
            self.assertEqual(client.get(f'/analyses/{task_id}').json()['status'], 'runner_error')


if __name__ == '__main__':
    unittest.main()
