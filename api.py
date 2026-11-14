"""Local, single-process API for trusted Python projects."""

from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timezone
import hashlib
import hmac
import json
from io import BytesIO
import ntpath
import os
from pathlib import Path, PureWindowsPath
import shutil
import secrets
import sqlite3
from tempfile import TemporaryDirectory
from threading import Lock
import uuid
from zipfile import BadZipFile, ZipFile

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBasic
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from generate_tests import generate_candidate, load_generation, model_settings, prepare_generation, save_manifest, validate_code
from run_analysis import ROOT, run_analysis

ZIP_LIMIT = 10 * 1024 * 1024


def unpack_project(data, destination):
    with ZipFile(BytesIO(data)) as archive:
        entries = archive.infolist()
        if len(entries) > 2000 or sum(entry.file_size for entry in entries) > 5 * ZIP_LIMIT:
            raise ValueError('ZIP 解壓後超過大小或檔案數上限。')
        for entry in entries:
            parts = entry.filename.rstrip('/').split('/')
            if any(not part or part in {'.', '..'} or part.endswith(('.', ' '))
                   or any(char in part for char in '\\:<>"|?*')
                   or (ntpath.isreserved(part) if hasattr(ntpath, 'isreserved')
                       else PureWindowsPath(part).is_reserved()) for part in parts):
                raise ValueError('ZIP 包含不支援的路徑。')
            if (entry.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError('ZIP 包含符號連結。')
            target = destination.joinpath(*parts)
            if entry.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(entry) as source, target.open('xb') as output:
                    shutil.copyfileobj(source, output)
    children = list(destination.iterdir())
    if len(children) == 1 and children[0].is_dir():
        return children[0]
    return destination


class ProjectRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    project: str | None = Field(default=None, min_length=1, max_length=4096)


class AnalysisRequest(ProjectRequest):
    timeout: int = Field(default=60, ge=1, le=300, strict=True)


class GenerationRequest(BaseModel):
    confirm: bool = Field(strict=True)


class CandidateRequest(GenerationRequest):
    code: str = Field(min_length=1, max_length=64000)


def create_app(reports_dir=None, runner=run_analysis, generated_dir=None, remote=False):
    reports = Path(reports_dir) if reports_dir is not None else ROOT / 'reports'
    database = reports / 'tasks.sqlite3'
    generated = Path(generated_dir) if generated_dir is not None else ROOT / 'generated'
    generation_lock = Lock()
    upload_lock = Lock()
    invite = os.getenv('CODESENTINEL_INVITE_PASSWORD', '') if remote else ''
    if remote and len(invite) < 20:
        raise RuntimeError('Set CODESENTINEL_INVITE_PASSWORD to a random password of at least 20 characters.')

    def project_path(value):
        if remote:
            raise HTTPException(status_code=404)
        try:
            path = (ROOT / (value or '.')).resolve()
            if path.is_dir():
                return path
        except (OSError, ValueError):
            pass
        raise HTTPException(status_code=422, detail='找不到指定的專案資料夾。')

    def generation_module(run_id, index, token):
        try:
            folder, manifest = load_generation(generated, run_id)
            if remote:
                digest = hashlib.sha256((token or '').encode()).hexdigest()
                if not hmac.compare_digest(manifest.get('access_digest', ''), digest):
                    raise FileNotFoundError
            if index < 1:
                raise IndexError
            entry = manifest['modules'][index - 1]
        except (FileNotFoundError, IndexError):
            raise HTTPException(status_code=404, detail='找不到此模組的預覽。') from None
        return folder, manifest, entry

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
        if remote:
            yield
            return
        with connect() as conn:
            conn.execute('''CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY, status TEXT NOT NULL, created_at TEXT NOT NULL,
                timeout INTEGER NOT NULL, result TEXT, message TEXT)''')
            if 'project' not in {row['name'] for row in conn.execute('PRAGMA table_info(tasks)')}:
                conn.execute('ALTER TABLE tasks ADD COLUMN project TEXT')
            # Only one Uvicorn process is supported. Interrupted jobs are not resumed.
            conn.execute("UPDATE tasks SET status = 'interrupted', message = 'Server restarted before task completion' WHERE status IN ('queued', 'running')")
        yield

    app = FastAPI(title='CodeSentinel AI', version='0.2.0', lifespan=lifespan,
                  description='Local test runner and candidate generation for trusted Python projects.')
    app.mount('/static', StaticFiles(directory=ROOT / 'web'), name='static')
    if remote:
        basic = HTTPBasic(auto_error=False)

        @app.middleware('http')
        async def authenticate(request, call_next):
            if request.url.path == '/health':
                return await call_next(request)
            try:
                credentials = await basic(request)
            except HTTPException:
                credentials = None
            if not credentials or not hmac.compare_digest(credentials.password.encode(), invite.encode()):
                return JSONResponse({'detail': '請輸入訪客密碼。'}, status_code=401,
                                    headers={'WWW-Authenticate': 'Basic realm="CodeSentinel AI"'})
            if request.method == 'POST' and request.headers.get('sec-fetch-site') == 'cross-site':
                return JSONResponse({'detail': '請從控制台操作。'}, status_code=403)
            response = await call_next(request)
            response.headers['Cache-Control'] = 'no-store'
            return response
    else:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost', 'testserver'])

    @app.get('/', include_in_schema=False)
    def dashboard():
        return FileResponse(ROOT / 'web' / 'index.html')

    def execute(task_id, timeout, project, candidate_code=None):
        try:
            with connect() as conn:
                conn.execute("UPDATE tasks SET status = 'running' WHERE id = ?", (task_id,))
            options = {'timeout': timeout, 'run_id': task_id, 'reports_dir': reports}
            if project is not None:
                options['project_dir'] = project
            if candidate_code is not None:
                options['candidate_code'] = candidate_code
            summary = runner(**options)
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

    @app.get('/settings')
    def settings():
        return {'remote': remote}

    @app.post('/generation/previews')
    def preview_generation(body: ProjectRequest):
        provider, model, key = model_settings()
        try:
            _, manifest = prepare_generation(project_path(body.project), generated, model, provider=provider)
        except (ValueError, OSError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None
        return {**manifest, 'configured': bool(model and (provider == 'ollama' or key))}

    @app.post('/generation/uploads')
    async def upload_project(request: Request):
        if request.headers.get('content-type') != 'application/zip':
            raise HTTPException(status_code=415, detail='請上傳 ZIP 檔。')
        if not upload_lock.acquire(blocking=False):
            raise HTTPException(status_code=409, detail='已有專案正在掃描。')
        try:
            data = bytearray()
            async for chunk in request.stream():
                if len(data) + len(chunk) > ZIP_LIMIT:
                    raise HTTPException(status_code=413, detail='ZIP 上限為 10 MB。')
                data.extend(chunk)
            return await run_in_threadpool(preview_upload, data)
        finally:
            upload_lock.release()

    def preview_upload(data):
        if remote:
            try:
                with TemporaryDirectory(dir=reports) as directory:
                    project = unpack_project(data, Path(directory))
                    provider, model, key = model_settings()
                    folder, manifest = prepare_generation(project, generated, model, provider=provider)
                token = secrets.token_urlsafe(32)
                manifest.pop('project', None)
                save_manifest(folder, {**manifest, 'access_digest': hashlib.sha256(token.encode()).hexdigest()})
                return {**manifest, 'access_token': token,
                        'configured': bool(model and (provider == 'ollama' or key))}
            except (BadZipFile, OSError, ValueError, RuntimeError, NotImplementedError):
                raise HTTPException(status_code=422, detail='ZIP 必須包含可讀取的 Python 原始碼。') from None

        destination = reports / 'uploads' / uuid.uuid4().hex
        destination.mkdir(parents=True)
        try:
            project = unpack_project(data, destination)
            return preview_generation(ProjectRequest(project=str(project.resolve())))
        except (BadZipFile, OSError, ValueError, RuntimeError, NotImplementedError, HTTPException) as exc:
            shutil.rmtree(destination)
            if isinstance(exc, HTTPException):
                raise
            raise HTTPException(status_code=422, detail='無法解壓此 ZIP，請檢查格式與檔案路徑。') from None

    @app.get('/generation/{run_id}/modules/{index}')
    def preview_module(run_id: str, index: int, request: Request):
        folder, _, entry = generation_module(run_id, index, request.headers.get('x-report-token'))
        directory = folder / entry['folder']
        candidate = directory / 'candidate.py.txt'
        diagnostics = directory / 'diagnostics.json'
        return {'request': json.loads((directory / 'request.json').read_text(encoding='utf-8')),
                'candidate': candidate.read_text(encoding='utf-8') if candidate.exists() else None,
                'findings': json.loads(diagnostics.read_text(encoding='utf-8')) if diagnostics.exists() else []}

    @app.post('/generation/{run_id}/modules/{index}')
    def generate_module(run_id: str, index: int, body: GenerationRequest, request: Request):
        if not body.confirm:
            raise HTTPException(status_code=422, detail='請確認要將模組內容送給模型。')
        provider, model, key = model_settings()
        if not model or (provider == 'openai' and not key):
            raise HTTPException(status_code=422, detail='請先設定 Ollama 模型或 OpenAI 模型與金鑰。')
        if not generation_lock.acquire(blocking=False):
            raise HTTPException(status_code=409, detail='已有模組正在生成測試。')
        try:
            folder, manifest, entry = generation_module(run_id, index, request.headers.get('x-report-token'))
            if manifest.get('provider', 'openai') != provider:
                raise HTTPException(status_code=422, detail='模型服務已變更，請重新掃描。')
            if entry['status'] == 'candidate':
                return preview_module(run_id, index, request)
            generate_candidate(folder, manifest, entry, model, key)
            return preview_module(run_id, index, request)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from None
        finally:
            generation_lock.release()

    @app.post('/analyses', status_code=202)
    def start_analysis(body: AnalysisRequest, background_tasks: BackgroundTasks):
        if remote:
            raise HTTPException(status_code=404)
        project = project_path(body.project) if body.project is not None else None
        return queue_analysis(background_tasks, body.timeout, project)

    @app.post('/generation/{run_id}/modules/{index}/analyses', status_code=202)
    def run_candidate(run_id: str, index: int, body: CandidateRequest, background_tasks: BackgroundTasks):
        if remote:
            raise HTTPException(status_code=404)
        if not body.confirm:
            raise HTTPException(status_code=422, detail='請確認你已核對候選測試並信任此專案。')
        _, manifest, entry = generation_module(run_id, index, None)
        if entry['status'] != 'candidate':
            raise HTTPException(status_code=409, detail='請先生成候選測試。')
        try:
            code = validate_code(body.code.strip())
        except (SyntaxError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=f'候選測試無法解析：{exc.msg if isinstance(exc, SyntaxError) else exc}') from None
        return queue_analysis(background_tasks, 60, project_path(manifest['project']), code)

    def queue_analysis(background_tasks, timeout, project, candidate_code=None):
        task_id = uuid.uuid4().hex
        created = datetime.now(timezone.utc).isoformat()
        with connect() as conn:
            # Serialize admission to avoid launching concurrent pytest jobs.
            conn.execute('BEGIN IMMEDIATE')
            active = conn.execute("SELECT id FROM tasks WHERE status IN ('queued', 'running') LIMIT 1").fetchone()
            if active:
                raise HTTPException(status_code=409, detail='An analysis is already active')
            conn.execute('INSERT INTO tasks (id, status, created_at, timeout, project) VALUES (?, ?, ?, ?, ?)',
                         (task_id, 'queued', created, timeout, str(project) if project else None))
        background_tasks.add_task(execute, task_id, timeout, project, candidate_code)
        return {'id': task_id, 'status': 'queued', 'status_url': f'/analyses/{task_id}'}

    @app.get('/analyses')
    def list_analyses(limit: int = Query(default=20, ge=1, le=100)):
        if remote:
            raise HTTPException(status_code=404)
        with connect() as conn:
            rows = conn.execute('SELECT id, status, created_at, timeout, message, project FROM tasks ORDER BY created_at DESC LIMIT ?', (limit,)).fetchall()
        return {'items': [dict(row) for row in rows]}

    @app.get('/analyses/{task_id}')
    def get_analysis(task_id: str):
        if remote:
            raise HTTPException(status_code=404)
        return read_task(task_id)

    return app


app = create_app()
