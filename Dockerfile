FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

WORKDIR /app
RUN addgroup --system app && adduser --system --ingroup app --uid 10001 app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY src ./src
COPY data ./data
COPY analysis ./analysis
RUN mkdir -p /app/runtime && chown -R app:app /app
USER 10001
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz')"
CMD ["uvicorn", "ti.api:app", "--app-dir", "src", "--host", "0.0.0.0", "--port", "8080", "--workers", "2"]
