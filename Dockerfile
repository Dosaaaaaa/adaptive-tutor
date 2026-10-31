# One image: the React front end is built in a first stage, then served by the Python API.
#   docker build -t adaptive-tutor .
#   docker run -p 8080:8080 -v tutor-data:/app/data -v "$PWD/.env:/app/.env:ro" adaptive-tutor
# API keys are read only from /app/.env (never from the environment), so mount the file as shown.
# The container runs as a non-root user. A .env that only you can read (mode 600) must be readable by that user, so if your
# user id is not 1000, build with: docker build --build-arg APP_UID=$(id -u) -t adaptive-tutor .

FROM node:22-alpine AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

FROM python:3.12-slim AS app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TUTOR_MODE=all
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY tutor/ tutor/
COPY api/ api/
COPY bank/ bank/
COPY --from=web /web/dist web/dist
ARG APP_UID=1000
RUN useradd --create-home --uid ${APP_UID} app && mkdir -p data && chown -R app:app /app/data /app/bank
USER app
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8080/api/health', timeout=4)"
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8080"]
