# ==============================
# STAGE 1 — BUILDER
# ==============================

FROM python:3.11 AS builder

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    make \
    automake \
    subversion \
    unixodbc-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /install

COPY requirements.txt .

RUN pip install --upgrade pip \
    && pip install --prefix=/install --no-cache-dir -r requirements.txt


# ==============================
# STAGE 2 — RUNTIME
# ==============================

FROM python:3.11-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
    nano \
    curl \
    unixodbc-dev \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /studio

# copiar dependencias instaladas
COPY --from=builder /install /usr/local

# copiar código
COPY . .

EXPOSE 8000