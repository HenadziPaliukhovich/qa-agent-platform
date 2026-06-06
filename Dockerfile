FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY backend/services/requirements.txt /app/backend/services/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/services/requirements.txt

COPY . /app

EXPOSE 8001 8002 8003 8004
