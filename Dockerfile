FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY web ./web

# Sin VOLUME: Railway no lo admite en el Dockerfile. Con DATABASE_URL (Postgres)
# no hace falta disco; si usas SQLite, monta un volumen en /app/data desde la
# plataforma.
EXPOSE 8000

# Un solo proceso: el bucle de tareas vive dentro.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers"]
