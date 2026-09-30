#!/usr/bin/env python3
"""asilmedia.org kuzatuvchisi: yangi kino yoki serial qismi chiqsa Telegramga xabar yuboradi.

Muhit o'zgaruvchilari:
  TELEGRAM_BOT_TOKEN  - @BotFather bergan token
  TELEGRAM_CHAT_ID    - xabar boradigan chat ID (bir nechta bo'lsa vergul bilan)
  STATE_FILE          - holat fayli (standart: state.json)
  PAGES               - /lastnews/ ning nechta sahifasi tekshiriladi (standart: 2)
"""
import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

BASE = "https://asilmedia.org"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
STATE_FILE = os.environ.get("STATE_FILE", os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json"))
PAGES = int(os.environ.get("PAGES", "2"))
MAX_STATE = 3000  # eng oxirgi N ta postni eslab qolamiz

CARD_RE = re.compile(r'<article class="card[^"]*"[^>]*>(.*?)</article>', re.S)
LINK_RE = re.compile(r'href="(https://asilmedia\.org/(\d+)-[^"]+\.html)"')
ALT_RE = re.compile(r'<img[^>]+src="([^"]+)"[^>]*alt="([^"]*)"')
BADGE_RE = re.compile(r'badge--series">([^<]+)<')
QUALITY_RE = re.compile(r'badge--(?:hd|quality)">([^<]+)<')

# Sarlavhadagi SEO dumini kesib tashlaymiz ("Uzbek tilida O'zbekcha tarjima ... skachat")
TAIL_RE = re.compile(r"\s+(Uzbek tilida|O'zbek tilida|Barcha qismlar|O'zbekcha tarjima).*$", re.I)


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def parse_cards(page_html):
    items = []
    for block in CARD_RE.findall(page_html):
        m = LINK_RE.search(block)
        if not m:
            continue
        url, pid = m.group(1), m.group(2)
        img = ALT_RE.search(block)
        badge = BADGE_RE.search(block)
        items.append({
            "id": pid,
            "url": url,
            "title": html.unescape(img.group(2)).strip() if img else url,
            "poster": urllib.parse.urljoin(BASE, img.group(1)) if img else None,
            "badge": html.unescape(badge.group(1)).strip() if badge else "",
            "quality": QUALITY_RE.findall(block),
        })
    return items


def short_title(title):
    t = TAIL_RE.sub("", title).strip()
    return t or title


def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def save_state(state):
    # Faqat eng yangi MAX_STATE ta postni saqlaymiz
    if len(state) > MAX_STATE:
        keep = sorted(state, key=lambda k: state[k].get("seen", 0), reverse=True)[:MAX_STATE]
        state = {k: state[k] for k in keep}
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1, sort_keys=True)
    os.replace(tmp, STATE_FILE)


def tg(method, token, data):
    req = urllib.request.Request(
        "https://api.telegram.org/bot%s/%s" % (token, method),
        data=json.dumps(data).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def notify(token, chat_ids, item, kind):
    head = "🎬 <b>Yangi kino/serial</b>" if kind == "new" else "📺 <b>Yangi qism</b>"
    lines = [head, "", "<b>%s</b>" % html.escape(short_title(item["title"]))]
    if item["badge"]:
        lines.append("🔹 %s" % html.escape(item["badge"]))
    if item["quality"]:
        lines.append("🎞 %s" % ", ".join(html.escape(q) for q in item["quality"]))
    text = "\n".join(lines)
    markup = {"inline_keyboard": [[{"text": "▶️ Ko'rish", "url": item["url"]}]]}
    for chat_id in chat_ids:
        try:
            if item["poster"]:
                tg("sendPhoto", token, {"chat_id": chat_id, "photo": item["poster"], "caption": text,
                                        "parse_mode": "HTML", "reply_markup": markup})
                continue
        except Exception as e:
            print("sendPhoto xato, matn yuboriladi:", e, file=sys.stderr)
        tg("sendMessage", token, {"chat_id": chat_id, "text": text, "parse_mode": "HTML",
                                  "reply_markup": markup, "disable_web_page_preview": True})
        time.sleep(0.5)


def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_ids = [c.strip() for c in os.environ.get("TELEGRAM_CHAT_ID", "").split(",") if c.strip()]
    dry = "--dry-run" in sys.argv or not (token and chat_ids)

    items = []
    for p in range(1, PAGES + 1):
        url = BASE + "/lastnews/" + ("" if p == 1 else "page/%d/" % p)
        items.extend(parse_cards(fetch(url)))
    # Takrorlarni olib tashlaymiz (bir post bir necha joyda chiqishi mumkin)
    seen_ids, unique = set(), []
    for it in items:
        if it["id"] not in seen_ids:
            seen_ids.add(it["id"])
            unique.append(it)
    if not unique:
        print("Sahifadan hech narsa topilmadi — sayt tuzilishi o'zgargan bo'lishi mumkin.", file=sys.stderr)
        sys.exit(1)

    state = load_state()
    first_run = state is None
    state = state or {}
    now = int(time.time())

    events = []
    for it in unique:
        old = state.get(it["id"])
        if old is None:
            events.append(("new", it))
        elif it["badge"] and it["badge"] != old.get("badge"):
            events.append(("episode", it))
        # "seen" faqat birinchi marta yoziladi — aks holda fayl har safar o'zgarib, keraksiz commit bo'ladi
        state[it["id"]] = {"badge": it["badge"] or (old or {}).get("badge", ""),
                           "title": short_title(it["title"]), "seen": (old or {}).get("seen", now)}

    if first_run:
        print("Birinchi ishga tushish: %d ta post eslab qolindi, xabar yuborilmadi." % len(unique))
    else:
        # Eskidan yangiga qarab yuboramiz
        for kind, it in reversed(events):
            print("[%s] %s — %s" % (kind, short_title(it["title"]), it["badge"]))
            if not dry:
                notify(token, chat_ids, it, kind)
        if not events:
            print("Yangilik yo'q.")
    if dry and not first_run:
        print("(dry-run: xabar yuborilmadi, TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID berilmagan)")
    save_state(state)


if __name__ == "__main__":
    main()
