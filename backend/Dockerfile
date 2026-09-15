FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt constraints.txt ./
RUN pip install --no-cache-dir -r requirements.txt -c constraints.txt
COPY alembic.ini docker-entrypoint.sh ./
COPY migrations ./migrations
COPY app ./app
# A new named volume copies this directory's ownership, so the unprivileged user can write attachments.
RUN useradd --create-home crm && mkdir -p /data/attachments && chown crm:crm /data/attachments
USER crm
EXPOSE 8000
ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
