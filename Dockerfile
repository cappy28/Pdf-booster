FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    ghostscript \
    build-essential \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir pymupdf --prefer-binary && \
    pip install --no-cache-dir \
        fastapi==0.111.0 \
        "uvicorn[standard]==0.30.0" \
        python-multipart==0.0.9 \
        Pillow==10.3.0

COPY main.py .

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
