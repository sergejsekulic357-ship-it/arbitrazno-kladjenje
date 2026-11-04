"""
Arbitrazno kladjenje - glavni program.

Pokretanje:  python app.py
- otvara stranicu http://127.0.0.1:5000 (kvote, arbitraze, kalkulator)
- u pozadini na svakih INTERVAL_MIN minuta povlaci kvote
- nove arbitraze salje na Telegram, ujutru salje izvestaj
"""

import os
import threading
import time
import webbrowser
from collections import deque
from datetime import datetime

from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory

load_dotenv()

import telegram  # noqa: E402  (posle load_dotenv da procita .env)
from igre import SPORTOVI  # noqa: E402
from kladionice import SAJTOVI, Citac  # noqa: E402
from pracenje import Pracenje  # noqa: E402
from pretraga import uporedi  # noqa: E402

INTERVAL_DAN = int(float(os.getenv("INTERVAL_MIN", "5")) * 60)
INTERVAL_NOC = int(float(os.getenv("INTERVAL_NOC_MIN", "15")) * 60)
NOC_OD = os.getenv("NOC_OD", "01:00")   # od tad do NOC_DO proverava rede
NOC_DO = os.getenv("NOC_DO", "07:00")
MIN_RAZMAK = 120                       # rucno osvezavanje najcesce na 2 min
ULOG = float(os.getenv("ULOG", "1000"))
JUTRO = os.getenv("JUTARNJI_IZVESTAJ", "07:00")


def interval():
    """Nocu se kvote retko menjaju - proveravamo rede, da ne opterecujemo sajtove."""
    sat = datetime.now().strftime("%H:%M")
    if NOC_OD <= NOC_DO:
        noc = NOC_OD <= sat < NOC_DO
    else:  # npr. 23:00 - 07:00, preko ponoci
        noc = sat >= NOC_OD or sat < NOC_DO
    return INTERVAL_NOC if noc else INTERVAL_DAN

stanje = {"mecevi": [], "arbitraze": [], "skoro": [], "osvezeno": None, "sledece": None,
          "u_toku": False, "sajtovi": {}, "zahteva": 0, "poruke": deque(maxlen=60)}
osvezi_sad = threading.Event()


def log(poruka):
    red = f"{datetime.now():%H:%M:%S}  {poruka}"
    print(red, flush=True)
    stanje["poruke"].appendleft(red)


citac = Citac(log)
pracenje = Pracenje(ULOG, log)


def ciklus():
    stanje["u_toku"] = True
    utakmice, po_sajtu = [], {s: 0 for s in SAJTOVI}
    for sport in SPORTOVI:
        for sajt in SAJTOVI:
            rez = citac.preuzmi(sajt, sport)
            if rez:
                utakmice.extend(rez)
                po_sajtu[sajt] += len(rez)
    mecevi, arbitraze, skoro = uporedi(utakmice)
    pracenje.azuriraj(arbitraze)
    stanje.update(mecevi=mecevi, arbitraze=arbitraze, skoro=skoro[:30],
                  osvezeno=time.time(), sajtovi=po_sajtu, zahteva=citac.ukupno_zahteva,
                  u_toku=False)
    log(f"osvezeno: {len(mecevi)} zajednickih utakmica, arbitraza {len(arbitraze)}, "
        f"skoro {len(skoro)} | utakmica po sajtu {po_sajtu}")


def petlja():
    danas = datetime.now().strftime("%Y-%m-%d")
    # ako je program pokrenut posle jutarnjeg termina - izvestaj tek sutra
    poslednji_izvestaj = danas if datetime.now().strftime("%H:%M") >= JUTRO else None

    while True:
        try:
            ciklus()
        except Exception as e:  # da jedna greska ne ugasi nocni rad
            stanje["u_toku"] = False
            log(f"GRESKA u ciklusu: {e!r}")
        poslednji = time.time()

        danas = datetime.now().strftime("%Y-%m-%d")
        if datetime.now().strftime("%H:%M") >= JUTRO and poslednji_izvestaj != danas:
            pracenje.jutarnji_izvestaj(stanje["arbitraze"])
            poslednji_izvestaj = danas
            log("poslat jutarnji izvestaj")

        stanje["sledece"] = poslednji + interval()
        while True:
            if osvezi_sad.wait(timeout=5):
                osvezi_sad.clear()
                if time.time() - poslednji >= MIN_RAZMAK:
                    break
            if time.time() - poslednji >= interval():
                break
            if (datetime.now().strftime("%H:%M") >= JUTRO
                    and poslednji_izvestaj != datetime.now().strftime("%Y-%m-%d")):
                break  # vreme za jutarnji izvestaj - prvo sveze kvote


app = Flask(__name__, static_folder="static")


@app.get("/")
def pocetna():
    return send_from_directory("static", "index.html")


@app.get("/api/stanje")
def api_stanje():
    # ako stranica vec ima ove kvote (?od=vreme_osvezavanja) - ne saljemo ih ponovo
    vec_ima = request.args.get("od") == str(stanje["osvezeno"])
    teski = {"mecevi": None, "arbitraze": None, "skoro": None} if vec_ima else {}
    return jsonify({**stanje, **teski, "poruke": list(stanje["poruke"]),
                    "imena_sajtova": {k: v["naziv"] for k, v in SAJTOVI.items()},
                    "ulog": ULOG, "min_razmak": MIN_RAZMAK, "telegram": telegram.podeseno()})


@app.post("/api/osvezi")
def api_osvezi():
    preostalo = MIN_RAZMAK - (time.time() - (stanje["osvezeno"] or 0))
    if preostalo > 0 or stanje["u_toku"]:
        return jsonify({"ok": False, "za_sekundi": max(0, int(preostalo))})
    osvezi_sad.set()
    return jsonify({"ok": True})


if __name__ == "__main__":
    log(f"Pokrecem: {len(SAJTOVI)} kladionice, {len(SPORTOVI)} sportova, osvezavanje na "
        f"{INTERVAL_DAN // 60} min (nocu {NOC_OD}-{NOC_DO} na {INTERVAL_NOC // 60} min), "
        f"jutarnji izvestaj u {JUTRO}, Telegram: "
        f"{'DA' if telegram.podeseno() else 'NE (nije podesen)'}")
    threading.Thread(target=petlja, daemon=True).start()
    threading.Timer(1.5, lambda: webbrowser.open("http://127.0.0.1:5000")).start()
    app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False)
