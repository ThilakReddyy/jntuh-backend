
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


RUN prisma generate



CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
