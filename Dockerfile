
FROM python:3.11.6-slim

WORKDIR /app

COPY requirements.txt .

# Install libatomic for Prisma and Python dependencies
RUN apt-get update && \
    apt-get install -y libatomic1 && \
    rm -rf /var/lib/apt/lists/* && \
    pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY . .



EXPOSE 8000


# Install a fixed Node release so Prisma does not select an unsupported prerelease.
ENV PRISMA_NODEENV_CACHE_DIR=/opt/prisma-nodeenv
RUN python -m nodeenv --node=22.23.5 "$PRISMA_NODEENV_CACHE_DIR" && \
    prisma generate



CMD sh -c "prisma db push && python main2.py & uvicorn main:app --host 0.0.0.0 --port 8000"


