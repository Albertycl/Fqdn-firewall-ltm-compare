# Pinned to the interpreter the requirements were pinned against.
FROM python:3.8-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Build tools are needed for the MySQL clients, then removed to keep the image small.
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc default-libmysqlclient-dev pkg-config curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && apt-get purge -y gcc pkg-config && apt-get autoremove -y

COPY backend/ /app/

COPY backend/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Configs are written here; mounted as a volume so they survive a rebuild.
ENV DOWNLOAD_DIR=/data/download
RUN mkdir -p /data/download

EXPOSE 5432

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["gunicorn", "--bind", "0.0.0.0:5432", "--workers", "4", "--timeout", "300", "main_ltm_fw:app"]
