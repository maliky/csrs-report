FROM node:24.18.0-alpine AS frontend

WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend ./
RUN npm run build

FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt ./
RUN apt-get update \
    && apt-get install --no-install-recommends --yes fonts-dejavu-core gzip libpq5 tar \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir -r requirements.txt
COPY . .
COPY --from=frontend /src/static/react ./static/react
RUN python manage.py collectstatic --noinput

ARG CSRS_GIT_SHA=unknown
LABEL org.opencontainers.image.revision="${CSRS_GIT_SHA}"

EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "60"]
