import os
import time
import json
import sqlite3
import feedparser
import requests

CONFIG_PATH = "config.json"
DB_PATH = "seen.db"

SLACK_TOKEN = os.getenv("SLACK_BOT_TOKEN")  # xoxb-...
SLACK_CHANNEL_ID = os.getenv("SLACK_CHANNEL_ID")  # C0XXXXXXX
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
    conn.execute("CREATE TABLE IF NOT EXISTS seen (id TEXT PRIMARY KEY)")
    conn.commit()
    return conn


def has_seen(conn, paper_id):
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM seen WHERE id = ?", (paper_id,))
    return cursor.fetchone() is not None


def mark_seen(conn, paper_id):
    try:
        conn.execute("INSERT INTO seen (id) VALUES (?)", (paper_id,))
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
    headers = {
        "Authorization": f"Bearer {SLACK_TOKEN}",
        "Content-Type": "application/json",
    }
    data = {
        "channel": SLACK_CHANNEL_ID,
        "text": f"[{feed_name}] *{entry.title}*\nBy: {entry.author}\n<{entry.link}|View on arXiv>",
    }
    response = requests.post(
        "https://slack.com/api/chat.postMessage", headers=headers, json=data
    )
    if not response.ok or not response.json().get("ok"):
        print(f"❌ Slack API error: {response.text}")


def run():
    conn = init_db()
    while True:
        feeds, keywords, authors = load_config()
        print(f"🔄 Checking {len(feeds)} feeds with {len(keywords)} keywords...")
        for feed_url in feeds:
            feed = feedparser.parse(feed_url)
            feed_name = feed_url.split("/")[-1]
            for entry in feed.entries:
                if not has_seen(conn, entry.id) and matches(entry, keywords, authors):
                    print(f"📌 New match: {entry.title}")
                    notify(entry, feed_name)
                    mark_seen(conn, entry.id)
            time.sleep(2)
        print("⏳ Sleeping...\n")
        time.sleep(INTERVAL)


if __name__ == "__main__":
    run()
