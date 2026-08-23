
FROM python:3.11.6-slim

WORKDIR /app

COPY requirements.txt .

# Install libatomic for Prisma/Python deps, curl for the container HEALTHCHECK
RUN apt-get update && \
    apt-get install -y libatomic1 curl && \
    rm -rf /var/lib/apt/lists/* && \
    pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY . .



EXPOSE 8000
EXPOSE 8001


RUN prisma generate



HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/api/health/live || exit 1

CMD sh -c "prisma db push && python main2.py & uvicorn main:app --host 0.0.0.0 --port 8000"


