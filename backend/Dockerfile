FROM python:3.12-slim
WORKDIR /app
# fonts-dejavu-core gives PDF report export (reportlab) a Cyrillic-capable TTF; reportlab's own bundled
# Vera.ttf has no Cyrillic glyphs. See app/reports.py's font resolution.
RUN apt-get update && apt-get install -y --no-install-recommends fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt constraints.txt ./
RUN pip install --no-cache-dir -r requirements.txt -c constraints.txt
COPY alembic.ini docker-entrypoint.sh ./
COPY migrations ./migrations
COPY app ./app
# A new named volume copies this directory's ownership, so the unprivileged user can write attachments.
RUN useradd --create-home crm && mkdir -p /data/attachments /data/reports && chown crm:crm /data/attachments /data/reports
USER crm
EXPOSE 8000
ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
