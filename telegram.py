"""
Telegram: slanje poruka (sa dugmadima) i primanje komandi.
Ako TELEGRAM_TOKEN/TELEGRAM_CHAT_ID nisu podeseni - ne radi nista.

Bot prihvata komande i klikove SAMO iz chata TELEGRAM_CHAT_ID (tvoj chat ili tvoja grupa),
da niko drugi ko nadje bota ne moze da ga koristi.
"""

import os

import requests


def podeseno():
    return bool(os.getenv("TELEGRAM_TOKEN") and os.getenv("TELEGRAM_CHAT_ID"))


def _api(metod, cekanje=15, **podaci):
    """cekanje = koliko Python ceka odgovor (NE Telegramov parametar 'timeout')."""
    try:
        r = requests.post(f"https://api.telegram.org/bot{os.getenv('TELEGRAM_TOKEN')}/{metod}",
                          json=podaci, timeout=cekanje)
        return r.json() if r.ok else None
    except (requests.RequestException, ValueError):
        return None


def _tastatura(dugmad):
    """dugmad: lista redova, red = lista (tekst, podatak)."""
    return {"inline_keyboard": [[{"text": t, "callback_data": d} for t, d in red] for red in dugmad]}


def posalji(tekst, dugmad=None):
    if not podeseno():
        return False
    podaci = {"chat_id": os.getenv("TELEGRAM_CHAT_ID"), "text": tekst,
              "parse_mode": "HTML", "disable_web_page_preview": True}
    if dugmad:
        podaci["reply_markup"] = _tastatura(dugmad)
    return bool(_api("sendMessage", **podaci))


def izmeni(chat_id, poruka_id, tekst):
    """Posle klika na dugme: zameni tekst poruke i skloni dugmad."""
    _api("editMessageText", chat_id=chat_id, message_id=poruka_id, text=tekst,
         parse_mode="HTML", disable_web_page_preview=True)


def potvrdi_klik(klik_id, tekst=""):
    _api("answerCallbackQuery", callback_query_id=klik_id, text=tekst)


def postavi_komande():
    """Da Telegram prikaze meni sa komandama (dugme '/' u chatu)."""
    _api("setMyCommands", commands=[
        {"command": "stanje", "description": "Balans simulacije i profit"},
        {"command": "arbitraze", "description": "Arbitraze koje sada vaze"},
        {"command": "otvoreni", "description": "Tiketi koji cekaju rezultat"},
        {"command": "pomoc", "description": "Sta bot ume"},
    ])


def prijem(obradi_poruku, obradi_klik, log=print):
    """
    Beskonacna petlja (pokrece se u posebnoj niti). Telegram drzi vezu otvorenu do 25 s
    i odgovori cim stigne nesto novo ("long polling") - to su zahtevi ka Telegramu,
    ne ka kladionicama.
    """
    import time
    pomeraj = None
    moj_chat = str(os.getenv("TELEGRAM_CHAT_ID"))
    while True:
        podaci = {"timeout": 25, "allowed_updates": ["message", "callback_query"]}
        if pomeraj:
            podaci["offset"] = pomeraj
        r = _api("getUpdates", cekanje=35, **podaci)
        if not r or not r.get("ok"):
            time.sleep(10)
            continue
        for u in r["result"]:
            pomeraj = u["update_id"] + 1
            try:
                if "message" in u:
                    m = u["message"]
                    if str(m["chat"]["id"]) == moj_chat and m.get("text"):
                        obradi_poruku(m["text"].strip())
                elif "callback_query" in u:
                    k = u["callback_query"]
                    poruka = k.get("message") or {}
                    if str(poruka.get("chat", {}).get("id")) == moj_chat:
                        obradi_klik(k["id"], k.get("data", ""), poruka["chat"]["id"],
                                    poruka.get("message_id"), poruka.get("text", ""))
                    else:
                        potvrdi_klik(k["id"], "Nije dozvoljeno")
            except Exception as e:  # jedna losa poruka ne sme da ugasi bota
                log(f"Telegram: greska pri obradi ({e!r})")
