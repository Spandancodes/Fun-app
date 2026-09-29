FROM node:22-bookworm-slim AS frontend-build
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
# Build from a distribution-safe public directory. User uploads with unclear
# redistribution rights and the real UPI payment image never enter the image.
RUN mkdir -p /tmp/distribution-safe/public/audio && \
    cp -R public/. /tmp/distribution-safe/public/ && \
    rm -f /tmp/distribution-safe/public/upi-scanner.jpeg \
      /tmp/distribution-safe/public/audio/login_wrong.mp3 \
      /tmp/distribution-safe/public/audio/no_first.mp3 \
      /tmp/distribution-safe/public/audio/yes_date_song.mp3 && \
    find /tmp/distribution-safe/public/audio -type f \( -name '*.mpeg' -o -name '*.mpeg3' \) -delete && \
    rm -rf public && cp -R /tmp/distribution-safe/public ./public
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
