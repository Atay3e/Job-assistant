FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV JOB_ASSISTANT_HOST=0.0.0.0
ENV JOB_ASSISTANT_DATA_DIR=/data/app-data
ENV JOB_ASSISTANT_WORKSPACE_DIR=/data/workspace

WORKDIR /app

COPY app/requirements.txt ./requirements.txt
RUN python -m pip install --no-cache-dir -r requirements.txt \
    && python -m playwright install --with-deps chromium

COPY app/ ./
RUN mkdir -p /data/app-data /data/workspace

EXPOSE 8787

CMD ["python", "server.py"]
