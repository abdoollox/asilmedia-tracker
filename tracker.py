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
SERIAL_RE = re.compile(r"serial|qism|mavsum|\d+-fasl|anime", re.I)


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
                "quality": ", ".join(AM_QUALITY_RE.findall(block)),
                "extra": "",
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
        date = _tag(block, "pubDate")
        items.append({
            "id": m.group(1),
            "url": url,
            "title": title,
            "poster": html.unescape(enc.group(1)) if enc else None,
            # Serial sanasi o'zgarsa — yangi qism; film sanasi o'zgarsa — yangilangan (sifatliroq) versiya
            "badge": date if is_serial else "",
            "badge_label": "",
            "date": "" if is_serial else date,
            "quality": "",
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
        if key.startswith("_"):  # "_order" kabi xizmat yozuvlari
            continue
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


def tg_upload_photo(token, fields, photo_url):
    """Telegram rasm URL'ini o'zi yuklay olmasa, rasmni biz yuklab, fayl sifatida jo'natamiz."""
    req = urllib.request.Request(photo_url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        img, ctype = r.read(), r.headers.get("Content-Type", "image/jpeg")
    boundary = "----tracker%d" % int(time.time() * 1000)
    body = b""
    for k, v in fields.items():
        if not isinstance(v, str):
            v = json.dumps(v)
        body += ("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n" % (boundary, k, v)).encode()
    fname = os.path.basename(urllib.parse.urlparse(photo_url).path) or "poster.jpg"
    body += ("--%s\r\nContent-Disposition: form-data; name=\"photo\"; filename=\"%s\"\r\nContent-Type: %s\r\n\r\n"
             % (boundary, fname, ctype)).encode() + img + ("\r\n--%s--\r\n" % boundary).encode()
    req = urllib.request.Request(
        "https://api.telegram.org/bot%s/sendPhoto" % token, data=body,
        headers={"Content-Type": "multipart/form-data; boundary=%s" % boundary},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


HEADS = {
    "new": "🎬 <b>Yangi kino/serial</b>",
    "upgrade": "⬆️ <b>Sifat yaxshilandi</b>",
    "update": "🔄 <b>Film yangilandi</b>\n<i>Sifatliroq versiya (WEB / BluRay) qo'shilgan bo'lishi mumkin</i>",
}


def format_message(src, item, kind):
    head = src["episode_head"] if kind == "episode" else HEADS[kind]
    lines = [
        "%s <b>%s</b> · #%s" % (src["emoji"], src["name"], src["key"]),
        head,
        "",
        "<b>%s</b>" % html.escape(short_title(item["title"])),
    ]
    if item["badge"] and item.get("badge_label", item["badge"]):
        lines.append("🔹 %s" % html.escape(item["badge"]))
    if item.get("old_quality") and item["quality"]:
        lines.append("🎞 %s → <b>%s</b>" % (html.escape(item["old_quality"]), html.escape(item["quality"])))
    elif item["quality"]:
        lines.append("🎞 %s" % html.escape(item["quality"]))
    if item["extra"]:
        lines.append("🏷 %s" % html.escape(item["extra"]))
    return "\n".join(lines)


def notify(token, chat_ids, src, item, kind):
    text = format_message(src, item, kind)
    markup = {"inline_keyboard": [[{"text": "▶️ %s'da ko'rish" % src["site"], "url": item["url"]}]]}
    for chat_id in chat_ids:
        if item["poster"]:
            fields = {"chat_id": chat_id, "caption": text, "parse_mode": "HTML", "reply_markup": markup}
            try:
                tg("sendPhoto", token, dict(fields, photo=item["poster"]))
                continue
            except Exception as e:
                print("sendPhoto (URL) xato, rasm yuklab jo'natiladi:", e, file=sys.stderr)
            try:
                tg_upload_photo(token, fields, item["poster"])
                continue
            except Exception as e:
                print("sendPhoto (fayl) xato, matn yuboriladi:", e, file=sys.stderr)
        tg("sendMessage", token, {"chat_id": chat_id, "text": text, "parse_mode": "HTML",
                                  "reply_markup": markup, "disable_web_page_preview": True})
        time.sleep(0.5)


# ---------------------------------------------------------------- asosiy
def _max_res(q):
    return max([int(x) for x in re.findall(r"(\d{3,4})p", q)] or [0])


def quality_improved(old, new):
    """480p -> 1080p kabi: eng yuqori o'lcham oshgan yoki yangi o'lcham qo'shilgan bo'lsa."""
    if not old or not new:
        return False
    old_set, new_set = set(re.findall(r"\d{3,4}p", old)), set(re.findall(r"\d{3,4}p", new))
    return _max_res(new) > _max_res(old) or new_set > old_set


def find_bumped(current, previous, posts):
    """Sanaga ko'ra tartiblangan ro'yxatda yuqoriga ko'tarilgan (yangilangan) eski postlarni topadi.

    Post X ko'tarilgan hisoblanadi, agar hozir X dan keyin turgan biror post avvalgi
    tekshiruvda X dan oldin turgan bo'lsa (yoki X avval ro'yxatda umuman bo'lmagan bo'lsa).
    """
    if not previous:
        return set()
    pidx = {pid: i for i, pid in enumerate(previous)}
    bumped, min_later = set(), float("inf")
    for pid in reversed(current):
        if pid in posts and pidx.get(pid, float("inf")) > min_later:
            bumped.add(pid)
        if pid in pidx:
            min_later = min(min_later, pidx[pid])
    return bumped


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
    orders = state.setdefault("_order", {})
    bumped = find_bumped([it["id"] for it in items], orders.get(src["key"]), posts)
    orders[src["key"]] = [it["id"] for it in items]

    events = []
    for it in items:
        old = posts.get(it["id"])
        is_serial = bool(it["badge"] or (old or {}).get("badge") or SERIAL_RE.search(it["title"]))
        if old is None:
            events.append(("new", it))
        elif is_serial:
            if it["badge"] and old.get("badge") and it["badge"] != old["badge"]:
                events.append(("episode", it))
        elif quality_improved(old.get("quality", ""), it["quality"]):
            it["old_quality"] = old["quality"]
            events.append(("upgrade", it))
        elif (it.get("date") and old.get("date") and it["date"] != old["date"]) or it["id"] in bumped:
            events.append(("update", it))
        # "seen" faqat birinchi marta yoziladi — aks holda fayl har safar o'zgarib, keraksiz commit bo'ladi
        rec = {"badge": it["badge"] or (old or {}).get("badge", ""),
               "title": short_title(it["title"]), "seen": (old or {}).get("seen", now)}
        for f in ("quality", "date"):
            if it.get(f):
                rec[f] = it[f]
        posts[it["id"]] = rec
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
            print("[%s] %s: %s — %s" % (src["key"], kind, short_title(it["title"]), it["badge"] or it["quality"]))
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
