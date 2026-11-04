"""
Citanje kvota sa kladionica.

MaxBet, Soccer, MerkurXtip i Oktagon koriste isti softver: jedan zahtev
po sportu vraca SVE utakmice tog sporta sa svim kvotama.

Zastita od blokade:
- pauza izmedju zahteva (PAUZA_SEKUNDI)
- ako sajt vrati 403/429, za njega se pravi pauza od 30 minuta
"""

import time

import requests

import telegram

SAJTOVI = {
    "maxbet": {"naziv": "MaxBet", "url": "https://www.maxbet.rs",
               "param": "annex=3&desktopVersion=1.2.1.10&locale=sr"},
    "soccer": {"naziv": "Soccer", "url": "https://www.soccerbet.rs",
               "param": "annex=0&desktopVersion=2.39.7&locale=sr"},
    "merkurxtip": {"naziv": "MerkurXtip", "url": "https://www.merkurxtip.rs",
                   "param": "annex=0&desktopVersion=2.39.7&locale=sr"},
    "oktagon": {"naziv": "Oktagon", "url": "https://www.oktagonbet.com",
                "param": "annex=0&desktopVersion=2.39.7&locale=sr"},
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/130.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "sr-RS,sr;q=0.9",
}

PAUZA_SEKUNDI = 2            # izmedju bilo koja dva zahteva
KAZNENA_PAUZA = 30 * 60      # posle 403/429 - toliko ne diramo taj sajt


class Citac:
    def __init__(self, log=print):
        self.log = log
        self.pauziran_do = {}      # sajt -> vreme do kad ne saljemo zahteve
        self.poslednji_zahtev = 0
        self.ukupno_zahteva = 0

    def _kvote(self, m):
        """Soccer cuva kvote u 'betMap', ostali u 'odds'. Vraca {kod: kvota}."""
        if "betMap" in m:
            out = {}
            for kod, po_liniji in m["betMap"].items():
                x = po_liniji.get("NULL")
                if x and x.get("ov"):
                    out[kod] = x["ov"]
            return out
        return {k: v for k, v in (m.get("odds") or {}).items() if v}

    def preuzmi(self, sajt, sport):
        """Vraca listu utakmica (samo one koje jos nisu pocele) ili None ako nije uspelo."""
        if time.time() < self.pauziran_do.get(sajt, 0):
            return None

        cekaj = PAUZA_SEKUNDI - (time.time() - self.poslednji_zahtev)
        if cekaj > 0:
            time.sleep(cekaj)

        s = SAJTOVI[sajt]
        url = f"{s['url']}/restapi/offer/sr/sport/{sport}/mob?{s['param']}"
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
        except requests.RequestException as e:
            self.log(f"{s['naziv']} {sport}: nema konekcije ({type(e).__name__})")
            return None
        finally:
            self.poslednji_zahtev = time.time()
            self.ukupno_zahteva += 1

        if r.status_code in (403, 429):
            self.pauziran_do[sajt] = time.time() + KAZNENA_PAUZA
            self.log(f"{s['naziv']}: odgovor {r.status_code} - PAUZA 30 min za ovaj sajt")
            # jedino upozorenje osim arbitraza - bitno zbog moguce blokade
            telegram.posalji(f"⚠️ {s['naziv']} je odbio zahtev ({r.status_code}). "
                             f"Pauziram ga 30 min da ne dodje do blokade.")
            return None
        if not r.ok:
            self.log(f"{s['naziv']} {sport}: greska {r.status_code}")
            return None

        try:
            podaci = r.json().get("esMatches") or []
        except ValueError:
            self.log(f"{s['naziv']} {sport}: odgovor nije JSON")
            return None

        sada_ms = time.time() * 1000
        rezultat = []
        for m in podaci:
            if m.get("live") or m.get("blocked") or m.get("kickOffTime", 0) <= sada_ms:
                continue
            if not m.get("brMatchId"):
                continue
            rezultat.append({
                "sajt": sajt,
                "sport": sport,
                "br": str(m["brMatchId"]),
                "domacin": m.get("home", ""),
                "gost": m.get("away", ""),
                "liga": m.get("leagueName", ""),
                "pocetak_ms": m["kickOffTime"],
                "kvote": self._kvote(m),
            })
        return rezultat
