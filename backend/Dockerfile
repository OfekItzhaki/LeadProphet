FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

RUN addgroup --system leadprophet && adduser --system --ingroup leadprophet leadprophet
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini
COPY app ./app
COPY scripts ./scripts
RUN chown -R leadprophet:leadprophet /app
USER leadprophet

EXPOSE 8000
CMD ["sh", "-c", "python -m alembic upgrade head && exec python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers"]
