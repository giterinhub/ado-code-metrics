# syntax=docker/dockerfile:1
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY src ./src

ENV PYTHONUNBUFFERED=1
CMD ["python", "-m", "src.ado_lang_inspector", "--out", "out/"]
