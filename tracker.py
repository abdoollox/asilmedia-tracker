#!/usr/bin/env python3
"""Kino saytlari kuzatuvchisi: yangi kino yoki serial qismi chiqsa Telegramga xabar yuboradi.

Kuzatiladigan saytlar: asilmedia.org, uzmovi.net

Muhit o'zgaruvchilari:
  TELEGRAM_BOT_TOKEN  - @BotFather bergan token
  TELEGRAM_CHAT_ID    - xabar boradigan chat ID (bir nechta bo'lsa vergul bilan)
  STATE_FILE          - holat fayli (standart: state.json)
"""
import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
STATE_FILE = os.environ.get("STATE_FILE", os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json"))
MAX_STATE = 3000  # har bir sayt uchun eng oxirgi N ta postni eslab qolamiz

# Sarlavhadagi SEO dumini kesib tashlaymiz ("Uzbek tilida O'zbekcha tarjima ... skachat")
TAIL_RE = re.compile(r"\s+(uzbek o'zbek tilida|uzbek tilida|o'zbek tilida|barcha qismlar|o'zbekcha tarjima"
                     r"|onlayn ko'rish).*$", re.I)
SERIAL_RE = re.compile(r"serial|qism|mavsum|fasl|anime", re.I)


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def short_title(title):
    t = TAIL_RE.sub("", title).strip()
    return t or title


# ---------------------------------------------------------------- asilmedia.org
# RSS buzilgan, shuning uchun /lastnews/ sahifasidagi kartochkalarni o'qiymiz.
# Serial kartochkasida "4-fasl 7-qism!" belgisi bor — u o'zgarsa, yangi qism chiqqan.
AM_BASE = "https://asilmedia.org"
AM_CARD_RE = re.compile(r'<article class="card[^"]*"[^>]*>(.*?)</article>', re.S)
AM_LINK_RE = re.compile(r'href="(https://asilmedia\.org/(\d+)-[^"]+\.html)"')
AM_IMG_RE = re.compile(r'<img[^>]+src="([^"]+)"[^>]*alt="([^"]*)"')
AM_BADGE_RE = re.compile(r'badge--series">([^<]+)<')
AM_QUALITY_RE = re.compile(r'badge--(?:hd|quality)">([^<]+)<')


def asilmedia_items(pages=2):
    items = []
    for p in range(1, pages + 1):
        page_html = fetch(AM_BASE + "/lastnews/" + ("" if p == 1 else "page/%d/" % p))
        for block in AM_CARD_RE.findall(page_html):
            m = AM_LINK_RE.search(block)
            if not m:
                continue
            img = AM_IMG_RE.search(block)
            badge = AM_BADGE_RE.search(block)
            items.append({
                "id": m.group(2),
                "url": m.group(1),
                "title": html.unescape(img.group(2)).strip() if img else m.group(1),
                "poster": urllib.parse.urljoin(AM_BASE, img.group(1)) if img else None,
                "badge": html.unescape(badge.group(1)).strip() if badge else "",
                "extra": ", ".join(AM_QUALITY_RE.findall(block)),
            })
    return items


# ---------------------------------------------------------------- uzmovi.net
# RSS to'g'ri ishlaydi. Serial qismi belgisi yo'q; serialga qism qo'shilganda post
# yangi sana bilan yuqoriga ko'tariladi — shuni "badge" sifatida kuzatamiz.
UZ_ITEM_RE = re.compile(r"<item>(.*?)</item>", re.S)


def _tag(block, name):
    m = re.search(r"<%s>(.*?)</%s>" % (name, name), block, re.S)
    if not m:
        return ""
    v = m.group(1).strip()
    if v.startswith("<![CDATA["):
        v = v[9:-3]
    return html.unescape(v).strip()


def uzmovi_items():
    items = []
    for block in UZ_ITEM_RE.findall(fetch("https://uzmovi.net/rss.xml")):
        url = _tag(block, "link")
        m = re.search(r"/(\d+)-[^/]+\.html", url)
        if not m:
            continue
        title = _tag(block, "title")
        enc = re.search(r'<enclosure url="([^"]+)"', block)
        is_serial = bool(SERIAL_RE.search(title) or "/serialar/" in url)
        items.append({
            "id": m.group(1),
            "url": url,
            "title": title,
            "poster": html.unescape(enc.group(1)) if enc else None,
            # Faqat seriallar uchun sanani kuzatamiz: kino qayta tahrirlansa xabar kerak emas
            "badge": _tag(block, "pubDate") if is_serial else "",
            "badge_label": "",
            "extra": _tag(block, "category"),
        })
    return items


SOURCES = [
    {"key": "asilmedia", "name": "AsilMedia", "emoji": "🟦", "site": "asilmedia.org", "fetch": asilmedia_items,
     "episode_head": "📺 <b>Yangi qism</b>"},
    {"key": "uzmovi", "name": "UZMOVi", "emoji": "🟩", "site": "uzmovi.net", "fetch": uzmovi_items,
     "episode_head": "📺 <b>Serial yangilandi</b> (yangi qism)"},
]


# ---------------------------------------------------------------- holat
def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            state = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    # Eski format (faqat asilmedia, kalit = post ID) — yangi formatga o'tkazamiz
    if state and all(k.isdigit() for k in state):
        state = {"asilmedia": state}
    return state


def save_state(state):
    for key, posts in state.items():
        if len(posts) > MAX_STATE:
            keep = sorted(posts, key=lambda k: posts[k].get("seen", 0), reverse=True)[:MAX_STATE]
            state[key] = {k: posts[k] for k in keep}
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1, sort_keys=True)
    os.replace(tmp, STATE_FILE)


# ---------------------------------------------------------------- telegram
def tg(method, token, data):
    req = urllib.request.Request(
        "https://api.telegram.org/bot%s/%s" % (token, method),
        data=json.dumps(data).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def format_message(src, item, kind):
    head = "🎬 <b>Yangi kino/serial</b>" if kind == "new" else src["episode_head"]
    lines = [
        "%s <b>%s</b> · #%s" % (src["emoji"], src["name"], src["key"]),
        head,
        "",
        "<b>%s</b>" % html.escape(short_title(item["title"])),
    ]
    if item["badge"] and item.get("badge_label", item["badge"]):
        lines.append("🔹 %s" % html.escape(item["badge"]))
    if item["extra"]:
        lines.append("🎞 %s" % html.escape(item["extra"]))
    return "\n".join(lines)


def notify(token, chat_ids, src, item, kind):
    text = format_message(src, item, kind)
    markup = {"inline_keyboard": [[{"text": "▶️ %s'da ko'rish" % src["site"], "url": item["url"]}]]}
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


# ---------------------------------------------------------------- asosiy
def check_source(src, state, now):
    """Saytni tekshiradi va (kind, item) hodisalar ro'yxatini qaytaradi."""
    items, ids = [], set()
    for it in src["fetch"]():
        if it["id"] not in ids:  # bir post bir necha joyda chiqishi mumkin
            ids.add(it["id"])
            items.append(it)
    if not items:
        raise RuntimeError("hech narsa topilmadi — sayt tuzilishi o'zgargan bo'lishi mumkin")

    first_run = src["key"] not in state
    posts = state.setdefault(src["key"], {})
    events = []
    for it in items:
        old = posts.get(it["id"])
        if old is None:
            events.append(("new", it))
        elif it["badge"] and old.get("badge") and it["badge"] != old["badge"]:
            events.append(("episode", it))
        # "seen" faqat birinchi marta yoziladi — aks holda fayl har safar o'zgarib, keraksiz commit bo'ladi
        posts[it["id"]] = {"badge": it["badge"] or (old or {}).get("badge", ""),
                           "title": short_title(it["title"]), "seen": (old or {}).get("seen", now)}
    if first_run:
        print("[%s] birinchi ishga tushish: %d ta post eslab qolindi, xabar yuborilmadi." % (src["key"], len(items)))
        return []
    return events


def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_ids = [c.strip() for c in os.environ.get("TELEGRAM_CHAT_ID", "").split(",") if c.strip()]
    dry = "--dry-run" in sys.argv or not (token and chat_ids)

    state = load_state()
    now = int(time.time())
    failed = []
    for src in SOURCES:
        try:
            events = check_source(src, state, now)
        except Exception as e:
            # Bitta sayt ishlamasa ham qolganlari tekshirilaveradi
            print("[%s] XATO: %s" % (src["key"], e), file=sys.stderr)
            failed.append(src["key"])
            continue
        for kind, it in reversed(events):  # eskidan yangiga qarab yuboramiz
            print("[%s] %s: %s — %s" % (src["key"], kind, short_title(it["title"]), it["badge"]))
            if not dry:
                notify(token, chat_ids, src, it, kind)
        if not events:
            print("[%s] yangilik yo'q." % src["key"])
    if dry:
        print("(dry-run: xabar yuborilmadi)")
    save_state(state)
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
