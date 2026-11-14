FROM python:3.12-slim
WORKDIR /app
RUN useradd --create-home appuser && mkdir reports generated && chown appuser reports generated
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY api.py remote_api.py generate_tests.py run_analysis.py ./
COPY web/ web/
USER appuser
EXPOSE 8000
CMD ["sh", "-c", "exec python -m uvicorn remote_api:app --host 0.0.0.0 --port ${PORT:-8000}"]
