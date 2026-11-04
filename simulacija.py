"""
Simulacija (zamisljeni balans): svaka NOVA arbitraza se "uplati" sa SIM_ULOG dinara
po kvotama iz trenutka kad je nadjena. Kad se upise rezultat utakmice, tiket se zatvori
i profit ide u balans. Pravog novca nema - ovo je da vidimo koliko bi se zaradilo.

Sve se cuva kao dnevnik dogadjaja u podaci/simulacija.jsonl, pa posle restarta
program samo ponovo "odigra" dnevnik i dobije isto stanje.
  tiket     - nova uplata
  nestala   - arbitraza vise ne postoji na sajtovima (pamti se koliko je trajala)
  pitano    - poslato pitanje za rezultat na Telegram (da se ne pita dvaput)
  rezultat  - upisan rezultat (1 / X / 2) ili "otkazano" (ulozi se vracaju)
"""

import json
import os
import threading
import time
from datetime import datetime

from arbitraza import rasporedi_ulog

FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "podaci")
DNEVNIK = os.path.join(FOLDER, "simulacija.jsonl")

ZAOKRUZI_NA = 10          # ulozi kao u stvarnosti: 21.110, ne 21.107,53
REALNO_MIN = 10           # "realne" = arbitraze koje su trajale bar ovoliko minuta

# Koliko posle pocetka je utakmica sigurno gotova (sati) - tad pitamo za rezultat
TRAJANJE_SPORTA_H = {"S": 2.5, "H": 3.0, "HB": 2.0, "T": 4.0, "V": 3.0, "TT": 1.5, "B": 2.5}

# Sportovi bez neresenog - rezultat je samo 1 ili 2
BEZ_NERESENOG = {"T", "TT", "V"}


def dobitni_ishod(ishodi, rezultat):
    """
    rezultat: '1', 'X' ili '2' (konacan ishod utakmice).
    Vraca indeks ishoda tiketa koji prolazi. Grupe igara pokrivaju sve ishode tacno
    jednom, pa uvek prolazi tacno jedan: npr. za '1 protiv X2' i rezultat X prolazi 'X2'.
    """
    for n, i in enumerate(ishodi):
        if rezultat in i["naziv"]:
            return n
    return None


class Simulacija:
    def __init__(self, ulog=100_000, log=print, dnevnik=DNEVNIK):
        self.ulog = ulog
        self.log = log
        self.dnevnik = dnevnik
        self.lock = threading.Lock()
        self.tiketi = {}           # kljuc arbitraze -> tiket
        self.vidjena = {}          # kljuc -> poslednji put vidjena aktivna (za trajanje)
        self.max_po_sajtu = {}     # najvise novca istovremeno zarobljenog po kladionici
        os.makedirs(os.path.dirname(dnevnik), exist_ok=True)
        self._ucitaj()

    # ---------- dnevnik ----------
    def _upisi(self, dogadjaj, **podaci):
        zapis = {"vreme": datetime.now().isoformat(timespec="seconds"), "dogadjaj": dogadjaj, **podaci}
        with open(self.dnevnik, "a", encoding="utf-8") as f:
            f.write(json.dumps(zapis, ensure_ascii=False) + "\n")
        self._primeni(zapis)

    def _ucitaj(self):
        if not os.path.exists(self.dnevnik):
            return
        with open(self.dnevnik, encoding="utf-8") as f:
            for red in f:
                if red.strip():
                    self._primeni(json.loads(red))

    def _primeni(self, z):
        d = z["dogadjaj"]
        if d == "tiket":
            t = dict(z["tiket"])
            self.tiketi[t["kljuc"]] = t
            self._azuriraj_max()
            return
        t = self.tiketi.get(z.get("kljuc"))
        if d == "nestala" and t:
            t["trajanje_min"] = z["trajanje_min"]
        elif d == "pitano":
            for t in self.tiketi.values():
                if t["mec_id"] == z["mec_id"]:
                    t["pitano"] = True
        elif d == "rezultat":
            for t in self.tiketi.values():
                if t["mec_id"] == z["mec_id"] and t["status"] == "otvoren":
                    self._zatvori(t, z["rezultat"], z["vreme"])
            self._azuriraj_max()

    def _zatvori(self, t, rezultat, vreme):
        t["rezultat"], t["zatvoren"] = rezultat, vreme
        if rezultat == "otkazano":
            t["status"], t["isplata"], t["profit"] = "otkazan", t["ukupno"], 0.0
            return
        n = dobitni_ishod(t["ishodi"], rezultat)
        if n is None:
            return  # npr. 'X' u tenisu - ne bi trebalo da se desi; tiket ostaje otvoren
        i = t["ishodi"][n]
        t["status"] = "zavrsen"
        t["dobitni"] = i["naziv"]
        t["isplata"] = round(i["ulog"] * i["kvota"], 2)
        t["profit"] = round(t["isplata"] - t["ukupno"], 2)

    def _azuriraj_max(self):
        sada = {}
        for t in self.tiketi.values():
            if t["status"] == "otvoren":
                for i in t["ishodi"]:
                    sada[i["naziv_sajta"]] = sada.get(i["naziv_sajta"], 0) + i["ulog"]
        for s, v in sada.items():
            self.max_po_sajtu[s] = max(self.max_po_sajtu.get(s, 0), v)

    # ---------- posle svakog kruga ----------
    def azuriraj(self, arbitraze):
        """Nove arbitraze -> nov tiket. Vraca listu novih tiketa (za Telegram poruku)."""
        novi = []
        sada = time.time()
        with self.lock:
            aktivni = set()
            for a in arbitraze:
                k = a["kljuc"]
                aktivni.add(k)
                if k not in self.tiketi:
                    t = self._napravi_tiket(a)
                    self._upisi("tiket", tiket=t)
                    novi.append(self.tiketi[k])
                    self.log(f"SIMULACIJA: uplaceno {t['ukupno']:.0f} na {a['naziv']} ({a['igra']}), "
                             f"najmanje {t['min_profit']:+.0f}")
                self.vidjena[k] = sada
            # arbitraza je nestala -> zapamti koliko je trajala
            for k in list(self.vidjena):
                if k not in aktivni:
                    t = self.tiketi.get(k)
                    if t and "trajanje_min" not in t:
                        prvi = datetime.fromisoformat(t["uplaceno"]).timestamp()
                        self._upisi("nestala", kljuc=k,
                                    trajanje_min=round((self.vidjena[k] - prvi) / 60, 1))
                    del self.vidjena[k]
        return novi

    def _napravi_tiket(self, a):
        kvote = [i["kvota"] for i in a["ishodi"]]
        ulozi, ukupno, min_isplata = rasporedi_ulog(kvote, self.ulog, ZAOKRUZI_NA)
        broj = len(self.tiketi) + 1
        return {
            "broj": broj, "kljuc": a["kljuc"], "mec_id": a["mec_id"],
            "sport": a["mec_id"].split("-")[0], "sport_naziv": a["sport_naziv"],
            "naziv": a["naziv"], "liga": a["liga"], "pocetak_ms": a["pocetak_ms"],
            "igra": a["igra"], "profit_proc": a["profit_proc"],
            "ishodi": [{"naziv": i["naziv"], "naziv_sajta": i["naziv_sajta"], "kvota": i["kvota"],
                        "ulog": u} for i, u in zip(a["ishodi"], ulozi)],
            "ukupno": ukupno, "min_profit": round(min_isplata - ukupno, 2),
            "uplaceno": datetime.now().isoformat(timespec="seconds"),
            "status": "otvoren", "pitano": False,
        }

    # ---------- rezultat ----------
    def upisi_rezultat(self, mec_id, rezultat):
        """rezultat: '1', 'X', '2' ili 'otkazano'. Vraca broj zatvorenih tiketa."""
        with self.lock:
            otvoreni = [t for t in self.tiketi.values() if t["mec_id"] == mec_id and t["status"] == "otvoren"]
            if not otvoreni or rezultat not in ("1", "X", "2", "otkazano"):
                return 0
            if rezultat == "X" and otvoreni[0]["sport"] in BEZ_NERESENOG:
                return 0
            self._upisi("rezultat", mec_id=mec_id, rezultat=rezultat)
            return len(otvoreni)

    def za_pitati(self):
        """Utakmice koje su (skoro sigurno) gotove, a rezultat jos nije upisan ni pitan."""
        sada_ms = time.time() * 1000
        po_mecu = {}
        with self.lock:
            for t in self.tiketi.values():
                kraj = t["pocetak_ms"] + TRAJANJE_SPORTA_H.get(t["sport"], 3) * 3600_000
                if t["status"] == "otvoren" and not t.get("pitano") and sada_ms >= kraj:
                    po_mecu.setdefault(t["mec_id"], t)
        return list(po_mecu.values())

    def oznaci_pitano(self, mec_id):
        with self.lock:
            self._upisi("pitano", mec_id=mec_id)

    # ---------- pregled ----------
    def pregled(self):
        with self.lock:
            tiketi = sorted(self.tiketi.values(), key=lambda t: -t["broj"])
            zavrseni = [t for t in tiketi if t["status"] in ("zavrsen", "otkazan")]
            otvoreni = [t for t in tiketi if t["status"] == "otvoren"]
            realni = [t for t in zavrseni if t.get("trajanje_min", 0) >= REALNO_MIN]
            zarobljeno = {}
            for t in otvoreni:
                for i in t["ishodi"]:
                    zarobljeno[i["naziv_sajta"]] = zarobljeno.get(i["naziv_sajta"], 0) + i["ulog"]
            return {
                "ulog": self.ulog,
                "realno_min": REALNO_MIN,
                "broj": len(tiketi),
                "otvorenih": len(otvoreni),
                "zavrsenih": len(zavrseni),
                "ulozeno": round(sum(t["ukupno"] for t in tiketi), 2),
                "profit": round(sum(t["profit"] for t in zavrseni), 2),
                "ocekivano": round(sum(t["min_profit"] for t in otvoreni), 2),
                "profit_realno": round(sum(t["profit"] for t in realni), 2),
                "realnih": len(realni),
                "zarobljeno": zarobljeno,
                "max_po_sajtu": dict(self.max_po_sajtu),
                "tiketi": tiketi[:200],
            }

    def kratko(self):
        """Jedan pasus za Telegram (/stanje i jutarnji izvestaj)."""
        p = self.pregled()
        d = lambda x, z="": f"{x:{z},.0f}".replace(",", ".")  # noqa: E731  12.345
        return (f"🎮 <b>Simulacija</b> ({d(p['ulog'])} din po arbitraži)\n"
                f"Tiketa: {p['broj']} (otvoreno {p['otvorenih']}, završeno {p['zavrsenih']})\n"
                f"Uloženo ukupno: {d(p['ulozeno'])}\n"
                f"Profit završenih: <b>{d(p['profit'], '+')}</b>\n"
                f"Očekivano od otvorenih: {d(p['ocekivano'], '+')}\n"
                f"Realno (arbitraže koje su trajale {p['realno_min']}+ min): "
                f"{d(p['profit_realno'], '+')} od {p['realnih']} tiketa")
