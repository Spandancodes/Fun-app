FROM node:22-bookworm-slim AS frontend-build
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
# Authorized audio is versioned in public/audio and checked before and after export.
# The real UPI scanner remains excluded by .dockerignore.
ENV STATIC_EXPORT=true
RUN npm run build

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    STATIC_DIR=/app/frontend/out
WORKDIR /app
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/main.py backend/mailbox.py backend/invite.py ./backend/
COPY --from=frontend-build /build/frontend/out ./frontend/out
WORKDIR /app/backend
EXPOSE 10000
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-10000}"]
