FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY web ./web

# La base de datos vive en /app/data: monta ahí un volumen para no perderla.
VOLUME ["/app/data"]
EXPOSE 8000

# Un solo proceso: SQLite + bucle de tareas interno.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers"]
