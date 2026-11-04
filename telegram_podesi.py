"""
Podesavanje Telegram bota (pokreces jednom):
1. U Telegramu otvori @BotFather, posalji /newbot, izaberi ime -> dobijes TOKEN
2. U .env upisi:  TELEGRAM_TOKEN=tvoj_token
3. Otvori svog novog bota u Telegramu i posalji mu bilo koju poruku (npr. "zdravo")
4. Pokreni:  python telegram_podesi.py
   -> pronadje tvoj chat ID, upise ga u .env i posalje probnu poruku
"""

import os
import sys

import requests
from dotenv import load_dotenv

ENV = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
load_dotenv(ENV)
token = os.getenv("TELEGRAM_TOKEN")
if not token:
    sys.exit("U .env nema TELEGRAM_TOKEN. Vidi korak 1-2 na vrhu ovog fajla.")

r = requests.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=15).json()
if not r.get("ok"):
    sys.exit(f"Telegram odbija token: {r.get('description')}")

chatovi = {u["message"]["chat"]["id"]: u["message"]["chat"].get("first_name", "")
           for u in r["result"] if "message" in u}
if not chatovi:
    sys.exit("Bot jos nije dobio nijednu poruku. Posalji mu nesto u Telegramu pa pokreni ponovo.")

chat_id, ime = next(iter(chatovi.items()))
sadrzaj = open(ENV, encoding="utf-8").read()
if "TELEGRAM_CHAT_ID=" in sadrzaj:
    sadrzaj = "\n".join(f"TELEGRAM_CHAT_ID={chat_id}" if red.startswith("TELEGRAM_CHAT_ID=") else red
                        for red in sadrzaj.splitlines()) + "\n"
else:
    sadrzaj = sadrzaj.rstrip("\n") + f"\nTELEGRAM_CHAT_ID={chat_id}\n"
open(ENV, "w", encoding="utf-8").write(sadrzaj)

requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
              json={"chat_id": chat_id, "text": "✅ Bot za arbitraze je povezan!"}, timeout=15)
print(f"Gotovo! Chat ID {chat_id} ({ime}) upisan u .env, poslata probna poruka.")
