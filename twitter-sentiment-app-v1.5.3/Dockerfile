FROM node:24-alpine AS frontend
WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements-v2.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/*.py backend/stock_universe.json ./backend/
COPY --from=frontend /build/dist ./frontend/dist
RUN useradd --create-home appuser && mkdir /app/data && chown -R appuser:appuser /app
USER appuser
ENV TRADERSECHO_DB=/app/data/tradersecho.sqlite
EXPOSE 8000
CMD ["uvicorn", "backend.service:app", "--host", "0.0.0.0", "--port", "8000"]
