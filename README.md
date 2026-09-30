# Asilmedia Tracker

Kino saytlarini kuzatib, quyidagi hollarda Telegramga xabar yuboradi:
- 🎬 yangi kino yoki serial qo'shilganda
- 📺 serialga yangi qism qo'shilganda

Har 10 daqiqada tekshiriladi. Xabarning birinchi qatorida sayt nomi va hashtag bo'ladi:

| Sayt | Belgi | Qayerdan o'qiladi | Yangi qism qanday aniqlanadi |
|---|---|---|---|
| asilmedia.org | 🟦 AsilMedia `#asilmedia` | `/lastnews/` (2 sahifa) | kartochkadagi "3-fasl 2-qism" belgisi o'zgarsa |
| uzmovi.net | 🟩 UZMOVi `#uzmovi` | `/rss.xml` (60 ta post) | serial posti yangi sana bilan yuqoriga ko'tarilsa |

Yangi sayt qo'shish uchun `tracker.py` dagi `SOURCES` ro'yxatiga yozuv qo'shiladi.

## 1. Bot yaratish
1. Telegramda [@BotFather](https://t.me/BotFather) → `/newbot` → **token**ni nusxalang.
2. Yangi botingizga istalgan xabar yuboring (masalan, `/start`).
3. Brauzerda `https://api.telegram.org/bot<TOKEN>/getUpdates` ni oching; `"chat":{"id": ...}` dagi raqam sizning **chat ID**ingiz.

## 2. Kompyuterda sinab ko'rish
```bash
TELEGRAM_BOT_TOKEN=xxx TELEGRAM_CHAT_ID=123 python3 tracker.py
```
Birinchi ishga tushirishda faqat hozirgi postlar eslab qolinadi, xabar yuborilmaydi. Keyingi safar faqat yangilari keladi.

## 3. GitHub Actions'da ishlatish (bepul, kompyuter yoqiq turishi shart emas)
1. GitHub'da yangi **private** repo oching va shu papkani push qiling.
2. Settings → Secrets and variables → Actions → `TELEGRAM_BOT_TOKEN` va `TELEGRAM_CHAT_ID` qo'shing.
3. Actions → "Asilmedia tracker" → **Run workflow** (bir marta sinab ko'rish uchun).

Shundan keyin u har 10 daqiqada o'zi ishlaydi va `state.json` ni repoga saqlab boradi.
