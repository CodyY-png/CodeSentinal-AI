from contextlib import closing
import sqlite3
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from api import create_app


class ApiChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.reports = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_real_execution_and_history_survive_restart(self):
        with TestClient(create_app(self.reports)) as client:
            response = client.post('/analyses', json={'timeout': 60})
            self.assertEqual(response.status_code, 202)
            task_id = response.json()['id']
            task = client.get(f'/analyses/{task_id}').json()
            self.assertEqual(task['status'], 'passed')
            self.assertEqual(task['result']['counts']['passed'], 4)
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
