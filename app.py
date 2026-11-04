"""
Arbitrazno kladjenje - glavni program.

Pokretanje:  python app.py
- otvara stranicu http://127.0.0.1:5000 (kvote, arbitraze, kalkulator)
- u pozadini na svakih INTERVAL_MIN minuta povlaci kvote
- nove arbitraze salje na Telegram, ujutru salje izvestaj
- simulacija: svaku novu arbitrazu "uplati" sa SIM_ULOG dinara i prati rezultat
- Telegram bot prima komande (/stanje, /arbitraze, /otvoreni, /pomoc) i dugmad za rezultat
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
from kladionice import RUCNO, SAJTOVI, Citac  # noqa: E402
from pracenje import Pracenje, upisi_ciklus  # noqa: E402
from pretraga import uporedi  # noqa: E402
from simulacija import BEZ_NERESENOG, Simulacija  # noqa: E402

INTERVAL_DAN = int(float(os.getenv("INTERVAL_MIN", "5")) * 60)
INTERVAL_NOC = int(float(os.getenv("INTERVAL_NOC_MIN", "15")) * 60)
NOC_OD = os.getenv("NOC_OD", "01:00")   # od tad do NOC_DO proverava rede
NOC_DO = os.getenv("NOC_DO", "07:00")
MIN_RAZMAK = 120                       # rucno osvezavanje najcesce na 2 min
ULOG = float(os.getenv("ULOG", "1000"))
JUTRO = os.getenv("JUTARNJI_IZVESTAJ", "07:00")
SIM_ULOG = float(os.getenv("SIM_ULOG", "100000"))


def je_noc():
    sat = datetime.now().strftime("%H:%M")
    if NOC_OD <= NOC_DO:
        return NOC_OD <= sat < NOC_DO
    return sat >= NOC_OD or sat < NOC_DO  # npr. 23:00 - 07:00, preko ponoci


def interval():
    """Nocu se kvote retko menjaju - proveravamo rede, da ne opterecujemo sajtove."""
    return INTERVAL_NOC if je_noc() else INTERVAL_DAN

stanje = {"mecevi": [], "arbitraze": [], "skoro": [], "osvezeno": None, "sledece": None,
          "u_toku": False, "sajtovi": {}, "zahteva": 0, "poruke": deque(maxlen=60)}
osvezi_sad = threading.Event()


def log(poruka):
    red = f"{datetime.now():%H:%M:%S}  {poruka}"
    print(red, flush=True)
    stanje["poruke"].appendleft(red)


citac = Citac(log)
pracenje = Pracenje(ULOG, log)
simulacija = Simulacija(SIM_ULOG, log)


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
    novi_tiketi = simulacija.azuriraj(arbitraze)
    pracenje.azuriraj(arbitraze, {t["kljuc"]: t for t in novi_tiketi})
    stanje.update(mecevi=mecevi, arbitraze=arbitraze, skoro=skoro[:30],
                  osvezeno=time.time(), sajtovi=po_sajtu, zahteva=citac.ukupno_zahteva,
                  u_toku=False)
    log(f"osvezeno: {len(mecevi)} zajednickih utakmica, arbitraza {len(arbitraze)}, "
        f"skoro {len(skoro)} | utakmica po sajtu {po_sajtu}")
    upisi_ciklus("ciklus", utakmica=len(mecevi), arbitraza=len(arbitraze),
                 skoro=len(skoro), po_sajtu=po_sajtu, zahteva_ukupno=citac.ukupno_zahteva)


def petlja():
    danas = datetime.now().strftime("%Y-%m-%d")
    # ako je program pokrenut posle jutarnjeg termina - izvestaj tek sutra
    poslednji_izvestaj = danas if datetime.now().strftime("%H:%M") >= JUTRO else None
    upisi_ciklus("pokrenuto", interval_min=INTERVAL_DAN // 60, noc_min=INTERVAL_NOC // 60)
    rupe = []                 # periodi kad program nije radio (sleep) - za jutarnji izvestaj
    prethodni_pocetak = None

    while True:
        pocetak = time.time()
        # ako je od proslog kruga proslo mnogo vise od intervala -> racunar je spavao
        if prethodni_pocetak and pocetak - prethodni_pocetak > INTERVAL_NOC + 300:
            minuta = round((pocetak - prethodni_pocetak) / 60, 1)
            od = datetime.fromtimestamp(prethodni_pocetak).isoformat(timespec="seconds")
            rupe.append({"od": od, "minuta": minuta})
            upisi_ciklus("rupa", od=od, minuta=minuta)
            log(f"UPOZORENJE: program nije radio ~{minuta} min (racunar je verovatno spavao)")
        prethodni_pocetak = pocetak
        try:
            ciklus()
        except Exception as e:  # da jedna greska ne ugasi nocni rad
            stanje["u_toku"] = False
            log(f"GRESKA u ciklusu: {e!r}")
            upisi_ciklus("greska", poruka=repr(e))
        poslednji = time.time()

        danas = datetime.now().strftime("%Y-%m-%d")
        if datetime.now().strftime("%H:%M") >= JUTRO and poslednji_izvestaj != danas:
            pracenje.jutarnji_izvestaj(stanje["arbitraze"], rupe, simulacija.kratko())
            poslednji_izvestaj = danas
            rupe = []
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


# ---------------- Telegram bot ----------------
POMOC = ("🤖 <b>Bot za arbitraže</b>\n\n"
         "Sam ti javljam svaku novu arbitražu, jutarnji izveštaj u 07:00 i pitam za rezultat "
         "utakmica iz simulacije (ne noću).\n\n"
         "/stanje – balans simulacije i profit\n"
         "/arbitraze – arbitraže koje sada važe\n"
         "/otvoreni – tiketi koji čekaju rezultat (sa dugmadima)\n"
         "/pomoc – ova poruka\n\n"
         "⚠️ Simulacija je zamišljena – pravi novac se ne uplaćuje.")


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def dugmad_rezultat(t):
    m = t["mec_id"]
    red = [("1", f"r|{m}|1")] + ([] if t["sport"] in BEZ_NERESENOG else [("X", f"r|{m}|X")]) + [("2", f"r|{m}|2")]
    return [red, [("Otkazano / odloženo", f"r|{m}|otkazano")]]


def pitanje_tekst(t):
    dodatak = " (regularno vreme, bez produžetaka)" if t["sport"] == "H" else ""
    return (f"❓ <b>Kako je završila utakmica?</b>{dodatak}\n"
            f"{t['sport_naziv']}: <b>{esc(t['naziv'])}</b>\n"
            f"Počela {datetime.fromtimestamp(t['pocetak_ms'] / 1000):%d.%m. u %H:%M}\n"
            f"Klikni konačan ishod:")


def obradi_poruku(tekst):
    komanda = tekst.split()[0].split("@")[0].lower()
    if komanda in ("/start", "/pomoc", "/help"):
        telegram.posalji(POMOC)
    elif komanda == "/stanje":
        telegram.posalji(simulacija.kratko())
    elif komanda == "/arbitraze":
        a = stanje["arbitraze"]
        if not a:
            telegram.posalji("Trenutno nema arbitraža. Proveravam na svakih par minuta.")
        else:
            redovi = [f"🟢 <b>{x['profit_proc']:+.2f}%</b> {esc(x['naziv'])} – {x['igra']}" for x in a[:15]]
            telegram.posalji("<b>Arbitraže koje sada važe:</b>\n" + "\n".join(redovi) +
                             "\n\n⚠️ Pre uplate proveri kvote na sajtu!")
    elif komanda == "/otvoreni":
        p = simulacija.pregled()
        otvoreni = [t for t in p["tiketi"] if t["status"] == "otvoren"]
        if not otvoreni:
            telegram.posalji("Nema otvorenih tiketa. 👍")
            return
        vidjeni, pocele = set(), []
        for t in sorted(otvoreni, key=lambda x: x["pocetak_ms"]):
            if t["mec_id"] in vidjeni:
                continue
            vidjeni.add(t["mec_id"])
            if t["pocetak_ms"] < time.time() * 1000:
                pocele.append(t)
        telegram.posalji(f"📋 Otvorenih tiketa: {len(otvoreni)} (utakmica koje su počele: {len(pocele)})")
        for t in pocele[:10]:
            telegram.posalji(pitanje_tekst(t), dugmad_rezultat(t))
    else:
        telegram.posalji("Ne razumem. Pošalji /pomoc za spisak komandi.")


def obradi_klik(klik_id, podatak, chat_id, poruka_id, stari_tekst):
    delovi = podatak.split("|")
    if len(delovi) != 3 or delovi[0] != "r":
        telegram.potvrdi_klik(klik_id)
        return
    _, mec_id, rezultat = delovi
    n = simulacija.upisi_rezultat(mec_id, rezultat)
    if not n:
        telegram.potvrdi_klik(klik_id, "Već upisano (ili nije moguće)")
        return
    tiketi = [t for t in simulacija.pregled()["tiketi"] if t["mec_id"] == mec_id]
    profit = sum(t.get("profit", 0) for t in tiketi)
    natpis = "otkazano – ulozi vraćeni" if rezultat == "otkazano" else f"ishod {rezultat}"
    telegram.potvrdi_klik(klik_id, "Upisano ✅")
    telegram.izmeni(chat_id, poruka_id,
                    f"✅ <b>{esc(tiketi[0]['naziv'])}</b>: {natpis}\n"
                    f"Zatvoreno tiketa: {n}, profit <b>{f'{profit:+,.0f}'.replace(',', '.')}</b>")
    log(f"rezultat upisan preko Telegrama: {tiketi[0]['naziv']} -> {rezultat}")


def pitanja_petlja():
    """Svaki minut: ima li utakmica iz simulacije koje su gotove - pitaj za rezultat (ne nocu)."""
    while True:
        try:
            if telegram.podeseno() and not je_noc():
                for t in simulacija.za_pitati()[:5]:
                    if telegram.posalji(pitanje_tekst(t), dugmad_rezultat(t)):
                        simulacija.oznaci_pitano(t["mec_id"])
        except Exception as e:
            log(f"GRESKA u pitanjima: {e!r}")
        time.sleep(60)


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
                    "rucno": RUCNO,
                    "ulog": ULOG, "min_razmak": MIN_RAZMAK, "telegram": telegram.podeseno()})


@app.get("/api/simulacija")
def api_simulacija():
    return jsonify(simulacija.pregled())


@app.post("/api/sim/rezultat")
def api_sim_rezultat():
    d = request.get_json(force=True)
    n = simulacija.upisi_rezultat(str(d.get("mec_id")), str(d.get("rezultat")))
    if n:
        log(f"rezultat upisan na stranici: {d.get('mec_id')} -> {d.get('rezultat')}")
    return jsonify({"ok": bool(n), "zatvoreno": n})


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
    if telegram.podeseno():
        telegram.postavi_komande()
        threading.Thread(target=telegram.prijem, args=(obradi_poruku, obradi_klik, log), daemon=True).start()
        threading.Thread(target=pitanja_petlja, daemon=True).start()
    threading.Timer(1.5, lambda: webbrowser.open("http://127.0.0.1:5000")).start()
    app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False)
