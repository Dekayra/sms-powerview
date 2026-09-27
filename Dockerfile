# --- stage 1: build the React frontend ---
FROM node:20-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# --- stage 2: runtime ---
# Pure Python, stdlib-only serial reader - no vendor app, no native
# extensions, so linux/arm64 works directly with no cross-compat tricks
# needed. Also buildable for other architectures (e.g. amd64) if needed.
FROM python:3.12-slim

RUN mkdir -p /opt/app
WORKDIR /opt/app

COPY app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./
COPY --from=frontend-build /app/frontend/dist ./frontend/dist
COPY tools/probe_protocol.py tools/watch_status.py /opt/tools/

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python3 -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:5000/health', timeout=3).getcode()==200 else 1)"

CMD ["python3", "app.py"]
