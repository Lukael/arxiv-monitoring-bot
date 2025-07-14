FROM python:3.11-slim

WORKDIR /app
COPY arxiv_notifier.py .
COPY config.json .

RUN pip install feedparser requests

CMD ["python", "arxiv_notifier.py"]