import os
import time
import json
import feedparser
import requests
import sqlite3

DB_PATH = "seen.db"
CONFIG_PATH = "config.json"
WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")
INTERVAL = int(os.getenv("POLL_INTERVAL", 600))


def load_config():
    with open(CONFIG_PATH, "r") as f:
        config = json.load(f)
    return (
        config.get("feeds", []),
        config.get("keywords", []),
        config.get("authors", []),
    )


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS seen (id TEXT PRIMARY KEY)")
    conn.commit()
    return conn


def has_seen(conn, paper_id):
    c = conn.cursor()
    c.execute("SELECT 1 FROM seen WHERE id = ?", (paper_id,))
    return c.fetchone() is not None


def mark_seen(conn, paper_id):
    c = conn.cursor()
    try:
        c.execute("INSERT INTO seen (id) VALUES (?)", (paper_id,))
        conn.commit()
    except sqlite3.IntegrityError:
        pass


def matches(entry, keywords, authors):
    title = entry.title.lower()
    summary = entry.summary.lower()
    author = entry.get("author", "").lower()
    return any(k in title or k in summary for k in keywords) or any(
        a in author for a in authors
    )


def notify(entry, feed_name):
    text = f"[{feed_name}] *{entry.title}*\nBy: {entry.author}\n{entry.link}"
    requests.post(WEBHOOK_URL, json={"text": text})


def run():
    conn = init_db()
    while True:
        feeds, keywords, authors = load_config()
        print(f"🔄 Loaded {len(feeds)} feeds and {len(keywords)} keywords")

        for url in feeds:
            feed = feedparser.parse(url)
            feed_name = url.split("/")[-1]
            for entry in feed.entries:
                if not has_seen(conn, entry.id) and matches(entry, keywords, authors):
                    print(f"📌 Match: {entry.title}")
                    notify(entry, feed_name)
                    mark_seen(conn, entry.id)
        time.sleep(INTERVAL)


if __name__ == "__main__":
    run()
