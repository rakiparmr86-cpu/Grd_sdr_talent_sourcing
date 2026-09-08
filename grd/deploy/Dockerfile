FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

COPY requirements.txt requirements-postgres.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-postgres.txt

COPY grd ./grd
COPY agents ./agents
COPY alembic ./alembic
COPY alembic.ini ./

EXPOSE 8000
# create_all runs on startup for dev; for real deploys run `alembic upgrade head` first
CMD ["uvicorn", "grd.main:app", "--host", "0.0.0.0", "--port", "8000"]
