"""Slanje poruka na Telegram. Ako TELEGRAM_TOKEN/TELEGRAM_CHAT_ID nisu podeseni - ne radi nista."""

import os

import requests


def podeseno():
    return bool(os.getenv("TELEGRAM_TOKEN") and os.getenv("TELEGRAM_CHAT_ID"))


def posalji(tekst):
    if not podeseno():
        return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{os.getenv('TELEGRAM_TOKEN')}/sendMessage",
            json={"chat_id": os.getenv("TELEGRAM_CHAT_ID"), "text": tekst,
                  "parse_mode": "HTML", "disable_web_page_preview": True},
            timeout=15,
        )
        return r.ok
    except requests.RequestException:
        return False
