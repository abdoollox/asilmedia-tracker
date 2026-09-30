# Asilmedia Tracker

asilmedia.org saytini kuzatib, quyidagi hollarda Telegramga xabar yuboradi:
- 🎬 yangi kino yoki serial qo'shilganda
- 📺 serialga yangi qism qo'shilganda ("3-fasl 2-qism" belgisi o'zgarganda)

Har 10 daqiqada `https://asilmedia.org/lastnews/` sahifasini (birinchi 2 sahifa) tekshiradi.

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
