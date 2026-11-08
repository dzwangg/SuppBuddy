# SuppBuddy backend container (Railway, Render, Fly, or any Docker host).
# Set ANTHROPIC_API_KEY on the host. Keep the database on a persistent volume, e.g. mount one at /data
# and set DATABASE_URL=sqlite:////data/suppbuddy.db; otherwise scans and crowd data reset on every restart.
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app app
COPY scripts scripts
COPY data/class_references.json data/tainted_supplements.csv data/
# One process on purpose: scans finish in background tasks inside it (app/pipeline.py).
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
