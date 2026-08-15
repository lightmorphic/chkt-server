FROM python:3.12-slim

WORKDIR /srv/chkt

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY run.py entrypoint.sh .
RUN chmod +x entrypoint.sh

ENV CHKT_DB=/data/chkt.db \
    CHKT_BACKUP_DIR=/data/backups

VOLUME /data
EXPOSE 8321

ENTRYPOINT ["./entrypoint.sh"]
# One worker on purpose: the due-reminder engine runs inside the app, and a
# second worker would fire every reminder twice. Threads handle concurrency.
CMD ["gunicorn", "-b", "0.0.0.0:8321", "--workers", "1", "--threads", "8", "run:app"]
