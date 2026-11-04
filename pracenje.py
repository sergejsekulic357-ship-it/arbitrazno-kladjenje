"""
Pracenje arbitraza kroz vreme (za test i nocni rad):
- kad se arbitraza pojavi -> zapis u podaci/arbitraze.jsonl + Telegram poruka
- kad nestane -> zapis koliko je trajala
- jutarnji izvestaj -> sta je nadjeno preko noci i sta i dalje vazi
"""

import json
import os
import time
from datetime import datetime

import telegram
from arbitraza import rasporedi_ulog

FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "podaci")
LOG = os.path.join(FOLDER, "arbitraze.jsonl")


def _vreme(ms):
    return datetime.fromtimestamp(ms / 1000).strftime("%d.%m. %H:%M")


def opis_za_poruku(a, ulog):
    kvote = [i["kvota"] for i in a["ishodi"]]
    ulozi, ukupno, min_isplata = rasporedi_ulog(kvote, ulog)
    redovi = [f"• <b>{i['naziv']}</b> @ {i['kvota']:.2f} na <b>{i['naziv_sajta']}</b> - ulog {u:.0f}"
              for i, u in zip(a["ishodi"], ulozi)]
    return (f"{a['sport_naziv']}: <b>{a['naziv']}</b> ({_vreme(a['pocetak_ms'])})\n"
            f"Igra: {a['igra']}\n" + "\n".join(redovi) +
            f"\nUlozeno {ukupno:.0f} → najmanja isplata {min_isplata:.0f} "
            f"(profit {min_isplata - ukupno:+.0f})")


class Pracenje:
    def __init__(self, ulog=1000, log=print):
        os.makedirs(FOLDER, exist_ok=True)
        self.ulog = ulog
        self.log = log
        self.aktivne = {}          # kljuc -> {"prvi": t, "poslednji": t, "max": proc, "a": zapis}
        self.noc = []              # sve nadjene od poslednjeg jutarnjeg izvestaja

    def _upisi(self, dogadjaj, **podaci):
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps({"vreme": datetime.now().isoformat(timespec="seconds"),
                                "dogadjaj": dogadjaj, **podaci}, ensure_ascii=False) + "\n")

    def azuriraj(self, arbitraze):
        sada = time.time()
        vidjene = set()
        for a in arbitraze:
            k = a["kljuc"]
            vidjene.add(k)
            if k not in self.aktivne:
                self.aktivne[k] = {"prvi": sada, "poslednji": sada, "max": a["profit_proc"], "a": a}
                self.noc.append(a)
                self._upisi("nova", **a)
                self.log(f"NOVA ARBITRAZA {a['profit_proc']:+.2f}%  {a['naziv']}  {a['igra']}")
                telegram.posalji(f"🟢 <b>ARBITRAZA {a['profit_proc']:+.2f}%</b>\n" +
                                 opis_za_poruku(a, self.ulog))
            else:
                z = self.aktivne[k]
                z["poslednji"], z["a"] = sada, a
                z["max"] = max(z["max"], a["profit_proc"])

        for k in list(self.aktivne):
            if k not in vidjene:
                z = self.aktivne.pop(k)
                trajanje = round((sada - z["prvi"]) / 60, 1)
                self._upisi("nestala", kljuc=k, naziv=z["a"]["naziv"], igra=z["a"]["igra"],
                            trajanje_min=trajanje, max_profit_proc=z["max"])
                # samo u zapisnik - na Telegram idu samo nove arbitraze i jutarnji izvestaj
                self.log(f"nestala: {z['a']['naziv']} {z['a']['igra']} (trajala ~{trajanje} min)")

    def jutarnji_izvestaj(self, arbitraze_sada):
        tekst = [f"☀️ <b>Jutarnji izvestaj</b>\nPreko noci nadjeno arbitraza: {len(self.noc)}"]
        if arbitraze_sada:
            tekst.append(f"\n<b>I dalje vaze ({len(arbitraze_sada)}):</b>")
            for a in arbitraze_sada[:10]:
                tekst.append(f"\n🟢 <b>{a['profit_proc']:+.2f}%</b> " + opis_za_poruku(a, self.ulog))
        else:
            tekst.append("Trenutno nema aktivnih arbitraza.")
        tekst.append("\n⚠️ Pre uplate proveri kvote na sajtu!")
        telegram.posalji("\n".join(tekst))
        self._upisi("jutarnji_izvestaj", nadjeno_noc=len(self.noc), aktivno=len(arbitraze_sada))
        self.noc = []
