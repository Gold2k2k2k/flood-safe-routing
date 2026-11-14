FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend

WORKDIR /app

# Install backend + ai-vision dependencies together for single-container Cloud Run deployment
COPY backend/requirements.txt /app/backend/requirements.txt
COPY ai-vision/requirements.txt /app/ai-vision/requirements.txt

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r /app/backend/requirements.txt -r /app/ai-vision/requirements.txt

COPY backend /app/backend
COPY ai-vision /app/ai-vision
COPY data /app/data

EXPOSE 8080

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
