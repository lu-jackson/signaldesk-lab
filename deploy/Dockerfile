# 公開展示站映像：前端 build → 後端 runtime（無 venv/測試依賴）
FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.14-slim
ENV PYTHONUNBUFFERED=1 PYTHONUTF8=1 SIGNALDESK_DB=/data/signaldesk.db
WORKDIR /app
COPY backend/requirements.runtime.txt ./
RUN pip install --no-cache-dir -r requirements.runtime.txt
COPY backend/app ./backend/app
COPY --from=web /web/dist ./frontend/dist
COPY deploy/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh && useradd -m app && mkdir /data && chown app /data
USER app
WORKDIR /app/backend
EXPOSE 8000
ENTRYPOINT ["/entrypoint.sh"]
