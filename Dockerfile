FROM python:3.11.6-slim
WORKDIR /app
COPY requirements.txt .
RUN apt-get update && \
    apt-get install -y libatomic1 && \
    rm -rf /var/lib/apt/lists/* && \
    pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt
# Avoid nodeenv's unpinned latest-version discovery selecting a prerelease.
RUN python -m nodeenv /root/.cache/prisma-python/nodeenv --node=22.14.0
COPY prisma ./prisma
RUN prisma generate
COPY . .
RUN chmod +x /app/entrypoint.sh
EXPOSE 8000
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
