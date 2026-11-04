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
CIKLUSI = os.path.join(FOLDER, "ciklusi.jsonl")   # svaki krug povlacenja (da se vide rupe/sleep)


def upisi_ciklus(dogadjaj, **podaci):
    """Kratak zapis svakog kruga. Ako racunar zaspi, ovde se vidi rupa u vremenu."""
    os.makedirs(FOLDER, exist_ok=True)
    with open(CIKLUSI, "a", encoding="utf-8") as f:
        f.write(json.dumps({"vreme": datetime.now().isoformat(timespec="seconds"),
                            "dogadjaj": dogadjaj, **podaci}, ensure_ascii=False) + "\n")


def _vreme(ms):
    return datetime.fromtimestamp(ms / 1000).strftime("%d.%m. %H:%M")


IKONE = {"S": "⚽", "B": "🏀", "T": "🎾", "TT": "🏓", "H": "🏒", "HB": "🤾", "V": "🏐"}


def _din(x, znak=False):
    """12345.6 -> '12.346' (srpski zapis hiljada)"""
    return (f"{x:+,.0f}" if znak else f"{x:,.0f}").replace(",", ".")


def _html(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def opis_za_poruku(a, ulog):
    """Pregledna poruka: utakmica, pa tabela 'ishod  kvota  kladionica  ulog'."""
    kvote = [i["kvota"] for i in a["ishodi"]]
    ulozi, ukupno, min_isplata = rasporedi_ulog(kvote, ulog, 10 if ulog >= 10_000 else 1)
    sport = a.get("mec_id", "").split("-")[0]
    sirina = max(len(i["naziv_sajta"]) for i in a["ishodi"])
    tabela = "\n".join(f"{i['naziv']:<3}{i['kvota']:>6.2f}  {i['naziv_sajta']:<{sirina}}  {_din(u):>7}"
                       for i, u in zip(a["ishodi"], ulozi))
    return (f"{IKONE.get(sport, '🎯')} <b>{_html(a['naziv'])}</b>\n"
            f"{a['sport_naziv']} · {_html(a['liga'])}\n"
            f"🕒 {_vreme(a['pocetak_ms'])} · {a['igra']}\n"
            f"<pre>{_html(tabela)}</pre>\n"
            f"💰 Uložiš {_din(ukupno)} → dobijaš najmanje {_din(min_isplata)} "
            f"(<b>{_din(min_isplata - ukupno, True)}</b>)")


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

    def azuriraj(self, arbitraze, sim_tiketi=None):
        """sim_tiketi: {kljuc: tiket} - nove uplate u simulaciji (da poruka to pomene)."""
        sim_tiketi = sim_tiketi or {}
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
                t = sim_tiketi.get(k)
                telegram.posalji(
                    f"🟢 <b>ARBITRAŽA {a['profit_proc']:+.2f}%</b>\n\n" +
                    opis_za_poruku(a, t["ukupno"] if t else self.ulog) +
                    (f"\n🎮 Uplaćeno u simulaciji (tiket #{t['broj']})" if t else "") +
                    "\n⚠️ Pre uplate proveri kvote na sajtu!")
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

    def jutarnji_izvestaj(self, arbitraze_sada, rupe=None, simulacija_tekst=""):
        tekst = [f"☀️ <b>Jutarnji izvestaj</b>\nPreko noci nadjeno arbitraza: {len(self.noc)}"]
        if rupe:
            ukupno = round(sum(r["minuta"] for r in rupe))
            tekst.append(f"⚠️ Program nije radio ukupno ~{ukupno} min (racunar je verovatno "
                         f"spavao) - noc nije cela pracena.")
        if arbitraze_sada:
            tekst.append(f"\n<b>I dalje vaze ({len(arbitraze_sada)}):</b>")
            for a in arbitraze_sada[:10]:
                tekst.append(f"\n🟢 <b>{a['profit_proc']:+.2f}%</b> " + opis_za_poruku(a, self.ulog))
        else:
            tekst.append("Trenutno nema aktivnih arbitraza.")
        if simulacija_tekst:
            tekst.append("\n" + simulacija_tekst)
        tekst.append("\n⚠️ Pre uplate proveri kvote na sajtu!")
        telegram.posalji("\n".join(tekst))
        self._upisi("jutarnji_izvestaj", nadjeno_noc=len(self.noc), aktivno=len(arbitraze_sada),
                    rupe_min=round(sum(r["minuta"] for r in rupe or [])))
        self.noc = []
