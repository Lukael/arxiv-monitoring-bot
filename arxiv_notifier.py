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


def send_config_summary(feeds, keywords, authors):
    headers = {
        "Authorization": f"Bearer {SLACK_TOKEN}",
        "Content-Type": "application/json",
    }

    summary = (
        "*📡 arXiv Notifier 시작됨!*\n"
        f"*Feeds:* {len(feeds)}개\n"
        + "\n".join([f"• `{f}`" for f in feeds])
        + f"\n\n*Keywords:* {', '.join(keywords) or '없음'}\n"
        + f"*Authors:* {', '.join(authors) or '없음'}"
    )

    data = {
        "channel": SLACK_CHANNEL_ID,
        "text": summary,
    }

    response = requests.post(
        "https://slack.com/api/chat.postMessage", headers=headers, json=data
    )
    if not response.ok or not response.json().get("ok"):
        print("❌ Config 알림 전송 실패:", response.text)


# --- Crossref Notifier ---
def run_crossref(conn):
    _, keywords, authors = load_config()
    for keyword in keywords:
        params = {
            "query.bibliographic": keyword,
            "sort": "published-online",
            "order": "desc",
            "rows": 1000,
            "filter": "from-online-pub-date:2024-01-01",
        }
        r = requests.get("https://api.crossref.org/works", params=params)
        if not r.ok:
            print(f"❌ Crossref error for keyword {keyword}: {r.text}")
            continue
        for item in r.json()["message"]["items"]:
            doi = item.get("DOI")
            if has_seen(conn, doi):
                continue
            title = item.get("title", [""])[0]
            print(title)
            authors_list = (
                [
                    f"{a.get('family','')} {a.get('given','')}"
                    for a in item.get("author", [])
                ]
                if "author" in item
                else []
            )
            author_string = ", ".join(authors_list) or "N/A"
            summary = item.get("abstract", "")
            date = item.get("published-online", {}).get("date-parts", [[]])[0]
            date_str = "-".join(str(x) for x in date)
            # print(date_str)
            if not (
                keyword.lower() in title.lower() or keyword.lower() in summary.lower()
            ):
                continue
            link = f"https://doi.org/{doi}"
            text = f"[Crossref] *{title}*\nBy: {author_string}\n<{link}|View DOI>"
            print(text)
            # mark_seen(conn, doi)
        time.sleep(2)


def run_arxiv(conn):
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


def run():
    conn = init_db()
    feeds, keywords, authors = load_config()
    send_config_summary(feeds, keywords, authors)
    while True:
        # run_arxiv(conn)
        run_crossref(conn)
        print("⏳ Sleeping...\n")
        break
        time.sleep(INTERVAL)


if __name__ == "__main__":
    run()
