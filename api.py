"""Local, single-process API for the trusted demo project."""

from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import uuid

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from run_analysis import ROOT, run_analysis


class AnalysisRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    timeout: int = Field(default=60, ge=1, le=300, strict=True)


def create_app(reports_dir=None, runner=run_analysis):
    reports = Path(reports_dir) if reports_dir is not None else ROOT / 'reports'
    database = reports / 'tasks.sqlite3'

    @contextmanager
    def connect():
        conn = sqlite3.connect(database, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def read_task(task_id):
        with connect() as conn:
            row = conn.execute('SELECT * FROM tasks WHERE id = ?', (task_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail='Task not found')
        result = dict(row)
        result['result'] = json.loads(result['result']) if result['result'] else None
        return result

    @asynccontextmanager
    async def lifespan(app):
        reports.mkdir(parents=True, exist_ok=True)
        with connect() as conn:
            conn.execute('''CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY, status TEXT NOT NULL, created_at TEXT NOT NULL,
                timeout INTEGER NOT NULL, result TEXT, message TEXT)''')
            # Only one Uvicorn process is supported. Interrupted jobs are not resumed.
            conn.execute("UPDATE tasks SET status = 'interrupted', message = 'Server restarted before task completion' WHERE status IN ('queued', 'running')")
        yield

    app = FastAPI(title='CodeSentinel AI', version='0.2.0', lifespan=lifespan,
                  description='Local demo API. Executes only the trusted tests/ suite. No LLM calls.')
    app.mount('/static', StaticFiles(directory=ROOT / 'web'), name='static')

    @app.get('/', include_in_schema=False)
    def dashboard():
        return FileResponse(ROOT / 'web' / 'index.html')

    def execute(task_id, timeout):
        try:
            with connect() as conn:
                conn.execute("UPDATE tasks SET status = 'running' WHERE id = ?", (task_id,))
            summary = runner(timeout=timeout, run_id=task_id, reports_dir=reports)
            with connect() as conn:
                conn.execute('UPDATE tasks SET status = ?, result = ? WHERE id = ?',
                             (summary['status'], json.dumps(summary, ensure_ascii=False), task_id))
        except Exception:
            # Keep an unexpected worker exception from leaving the task running forever.
            with connect() as conn:
                conn.execute("UPDATE tasks SET status = 'runner_error', message = 'Unexpected runner error' WHERE id = ?", (task_id,))

    @app.get('/health')
    def health():
        return {'status': 'ok'}

    @app.post('/analyses', status_code=202)
    def start_analysis(body: AnalysisRequest, background_tasks: BackgroundTasks):
        task_id = uuid.uuid4().hex
        created = datetime.now(timezone.utc).isoformat()
        with connect() as conn:
            # Serialize admission to avoid launching concurrent pytest jobs.
            conn.execute('BEGIN IMMEDIATE')
            active = conn.execute("SELECT id FROM tasks WHERE status IN ('queued', 'running') LIMIT 1").fetchone()
            if active:
                raise HTTPException(status_code=409, detail='An analysis is already active')
            conn.execute('INSERT INTO tasks (id, status, created_at, timeout) VALUES (?, ?, ?, ?)',
                         (task_id, 'queued', created, body.timeout))
        background_tasks.add_task(execute, task_id, body.timeout)
        return {'id': task_id, 'status': 'queued', 'status_url': f'/analyses/{task_id}'}

    @app.get('/analyses')
    def list_analyses(limit: int = Query(default=20, ge=1, le=100)):
        with connect() as conn:
            rows = conn.execute('SELECT id, status, created_at, timeout, message FROM tasks ORDER BY created_at DESC LIMIT ?', (limit,)).fetchall()
        return {'items': [dict(row) for row in rows]}

    @app.get('/analyses/{task_id}')
    def get_analysis(task_id: str):
        return read_task(task_id)

    return app


app = create_app()
