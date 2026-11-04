"""
Citanje kvota sa kladionica.

Svaki citac vraca utakmice u ISTOM obliku, pa ostatak programa ne zna
odakle stizu kvote:
    {"sajt", "sport", "br" (Betradar ID), "domacin", "gost", "liga",
     "pocetak_ms", "kvote": {kod: kvota}}
Kodovi kvota su kao kod MaxBet-a: 1/2/3 = 1/X/2, 7/8/9 = 1X/12/X2
(u sportovima bez neresenog: 1 i 3 = pobednik). Ostali sajtovi se
prevode u te kodove - SAMO za igre ciji smo naziv proverili.

Vrste sajtova:
- "ibet"      MaxBet, Soccer, MerkurXtip, Oktagon, Brazilbet, Betole, 365.rs (isti softver)
- "admiral"   AdmiralBet
- "superbet"  Superbet (podaci stizu kao tok - citamo samo pocetni snimak)
- "balkanbet" Balkanbet (NSoft sistem)

Zastita od blokade:
- pauza izmedju zahteva (PAUZA_SEKUNDI)
- ako sajt vrati 403/429, za njega se pravi pauza od 30 minuta
"""

import json
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import requests

import telegram

_IBET_STARI = "annex=0&desktopVersion=2.39.7&locale=sr"

SAJTOVI = {
    "maxbet": {"naziv": "MaxBet", "tip": "ibet", "url": "https://www.maxbet.rs",
               "param": "annex=3&desktopVersion=1.2.1.10&locale=sr"},
    "soccer": {"naziv": "Soccer", "tip": "ibet", "url": "https://www.soccerbet.rs", "param": _IBET_STARI},
    "merkurxtip": {"naziv": "MerkurXtip", "tip": "ibet", "url": "https://www.merkurxtip.rs",
                   "param": _IBET_STARI},
    "oktagon": {"naziv": "Oktagon", "tip": "ibet", "url": "https://www.oktagonbet.com", "param": _IBET_STARI},
    "brazilbet": {"naziv": "Brazilbet", "tip": "ibet", "url": "https://www.brazilbet.rs", "param": _IBET_STARI},
    "betole": {"naziv": "Betole", "tip": "ibet", "url": "https://www.betole.com", "param": _IBET_STARI},
    "365": {"naziv": "365.rs", "tip": "ibet", "url": "https://ibet2.365.rs", "param": _IBET_STARI},
    "admiral": {"naziv": "Admiral", "tip": "admiral"},
    "superbet": {"naziv": "Superbet", "tip": "superbet"},
    "balkanbet": {"naziv": "Balkanbet", "tip": "balkanbet"},
}

# Kladionice koje aplikacija NE cita (zastita ili jos nije uradjeno).
# Prikazuju se kao "proveri rucno" kod skoro-arbitraza.
RUCNO = [
    {"naziv": "Mozzart", "url": "https://www.mozzartbet.com/sr/kladjenje", "zasto": "zastita (Cloudflare)"},
    {"naziv": "Meridian", "url": "https://meridianbet.rs/sr/kladjenje/fudbal", "zasto": "zastita (token)"},
    {"naziv": "Volcano", "url": "https://www.volcanobet.rs/sport-v2/prematch/events", "zasto": "jos nije dodat"},
    {"naziv": "Ambassador", "url": "https://ambassadorbet.rs/sports-betting", "zasto": "jos nije dodat"},
    {"naziv": "Tasbet", "url": "https://tasbet.rs/sports-betting", "zasto": "jos nije dodat"},
    {"naziv": "Starbet", "url": "https://www.starbet.rs/Oblozuvanje.aspx", "zasto": "jos nije dodat"},
    {"naziv": "King", "url": "https://king.rs/sport/", "zasto": "jos nije dodat"},
    {"naziv": "1xBet", "url": "https://1xbet.rs/", "zasto": "ne moze se citati"},
    {"naziv": "bet365", "url": "https://www.bet365.rs/", "zasto": "ne moze se citati"},
]

# Brojevi sportova po sajtu (procitani iz menija sajtova 2026-11-04)
SPORT_ID = {
    "admiral": {"S": 1, "T": 3, "H": 4, "HB": 6, "TT": 17, "V": 20},
    "superbet": {"S": 5, "T": 2, "H": 3, "HB": 11, "TT": 24, "V": 1},
    "balkanbet": {"S": 18, "T": 78, "H": 21, "HB": 24, "V": 30, "TT": 69},
}

# Sportovi u kojima su nazivi igara PROVERENI za nove sajtove. Ostali se dodaju
# tek posle provere (lazna arbitraza = pravi gubitak).
# Provereno 2026-11-04: nazivi iz podataka sajta + poredjenje kvota sa onim sto pise na sajtu.
_SVI = ("S", "T", "H", "HB", "V", "TT")
PROVERENI_SPORTOVI = {
    "admiral": _SVI,
    "superbet": _SVI,
    "balkanbet": _SVI,
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/130.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "sr-RS,sr;q=0.9",
}

PAUZA_SEKUNDI = 2            # izmedju bilo koja dva zahteva
KAZNENA_PAUZA = 30 * 60      # posle 403/429 - toliko ne diramo taj sajt
SUPERBET_MAX_S = 60          # najduze citanje Superbet toka

BALKANBET_FIRMA = "4f54c6aa-82a9-475d-bf0e-dc02ded89225"


def _ms(tekst_utc):
    """'2026-11-04T13:45:00Z' ili '...000Z' -> milisekunde."""
    t = tekst_utc.replace("Z", "+00:00")
    return int(datetime.fromisoformat(t).timestamp() * 1000)


def _dvoje(naziv):
    """'Arsenal - Chelsea' -> ('Arsenal', 'Chelsea')"""
    if " - " in naziv:
        a, b = naziv.split(" - ", 1)
        return a.strip(), b.strip()
    return naziv, ""


# ---------- prevodjenje igara u zajednicke kodove ----------
# Samo proverene igre. Kljuc je (naziv igre malim slovima, naziv ishoda).
_KOD_1X2 = {"1": "1", "X": "2", "2": "3"}
_KOD_DUPLA = {"1X": "7", "12": "8", "X2": "9"}


def _prevedi(ishodi_po_igri):
    """
    ishodi_po_igri: {naziv_igre: {naziv_ishoda: kvota}}
    Vraca {kod: kvota}. Konacan ishod sa X -> 1/2/3; bez X (pobednik) -> 1 i 3.
    """
    kvote = {}
    for igra, ishodi in ishodi_po_igri.items():
        imena = set(ishodi)
        if igra in KONACAN_ISHOD:
            if imena == {"1", "X", "2"}:
                for ime, kod in _KOD_1X2.items():
                    kvote[kod] = ishodi[ime]
            elif imena == {"1", "2"}:
                kvote["1"], kvote["3"] = ishodi["1"], ishodi["2"]
        elif igra in DUPLA_SANSA and imena == {"1X", "12", "X2"}:
            for ime, kod in _KOD_DUPLA.items():
                kvote[kod] = ishodi[ime]
    return {k: v for k, v in kvote.items() if v and v > 1}


# Nazivi igara (malim slovima) koji znace konacan ishod / pobednika celog meca.
# Dodaje se tek kad se naziv potvrdi na sajtu.
KONACAN_ISHOD = {"konacan ishod", "konačan ishod",
                 # pobednik celog meca (tenis, odbojka, stoni tenis). NE "1.set - pobednik"
                 # i NE "pobednik (+ot+pen)" (hokej sa produzecima) - to su druge igre.
                 "pobednik", "pobednik meča", "pobednik meca"}
DUPLA_SANSA = {"dupla sansa", "dupla šansa"}


class Citac:
    def __init__(self, log=print):
        self.log = log
        self.pauziran_do = {}      # sajt -> vreme do kad ne saljemo zahteve
        self.poslednji_zahtev = 0
        self.ukupno_zahteva = 0
        self.nepoznate_igre = {}   # (sajt, sport) -> skup naziva igara (za proveru)

    # ---------- zajednicki deo: pauza, 403/429 ----------
    def _get(self, sajt, opis, url, **kw):
        """GET sa pauzom i zastitom. Vraca Response ili None."""
        if time.time() < self.pauziran_do.get(sajt, 0):
            return None
        cekaj = PAUZA_SEKUNDI - (time.time() - self.poslednji_zahtev)
        if cekaj > 0:
            time.sleep(cekaj)
        naziv = SAJTOVI[sajt]["naziv"]
        try:
            r = requests.get(url, timeout=30, **kw)
        except requests.RequestException as e:
            self.log(f"{naziv} {opis}: nema konekcije ({type(e).__name__})")
            return None
        finally:
            self.poslednji_zahtev = time.time()
            self.ukupno_zahteva += 1

        if r.status_code in (403, 429):
            r.close()
            self.pauziran_do[sajt] = time.time() + KAZNENA_PAUZA
            self.log(f"{naziv}: odgovor {r.status_code} - PAUZA 30 min za ovaj sajt")
            # jedino upozorenje osim arbitraza - bitno zbog moguce blokade
            telegram.posalji(f"⚠️ {naziv} je odbio zahtev ({r.status_code}). "
                             f"Pauziram ga 30 min da ne dodje do blokade.")
            return None
        if not r.ok:
            r.close()
            self.log(f"{naziv} {opis}: greska {r.status_code}")
            return None
        return r

    def preuzmi(self, sajt, sport):
        """Vraca listu utakmica (samo one koje jos nisu pocele) ili None ako nije uspelo."""
        tip = SAJTOVI[sajt]["tip"]
        if tip != "ibet" and sport not in PROVERENI_SPORTOVI.get(tip, ()):
            return None
        try:
            return getattr(self, "_" + tip)(sajt, sport)
        except (ValueError, KeyError, TypeError) as e:
            # sajt je promenio format - ne rusimo ceo krug zbog jednog sajta
            self.log(f"{SAJTOVI[sajt]['naziv']} {sport}: neocekivan odgovor ({e!r})")
            return None

    # ---------- MaxBet i isti softver ----------
    @staticmethod
    def _ibet_kvote(m):
        """Soccer cuva kvote u 'betMap', ostali u 'odds'. Vraca {kod: kvota}."""
        if "betMap" in m:
            out = {}
            for kod, po_liniji in m["betMap"].items():
                x = po_liniji.get("NULL")
                if x and x.get("ov"):
                    out[kod] = x["ov"]
            return out
        return {k: v for k, v in (m.get("odds") or {}).items() if v}

    def _ibet(self, sajt, sport):
        s = SAJTOVI[sajt]
        r = self._get(sajt, sport, f"{s['url']}/restapi/offer/sr/sport/{sport}/mob?{s['param']}",
                      headers=HEADERS)
        if r is None:
            return None
        podaci = r.json().get("esMatches") or []
        sada_ms = time.time() * 1000
        rezultat = []
        for m in podaci:
            if m.get("live") or m.get("blocked") or m.get("kickOffTime", 0) <= sada_ms:
                continue
            if not m.get("brMatchId"):
                continue
            rezultat.append({
                "sajt": sajt, "sport": sport, "br": str(m["brMatchId"]),
                "domacin": m.get("home", ""), "gost": m.get("away", ""),
                "liga": m.get("leagueName", ""), "pocetak_ms": m["kickOffTime"],
                "kvote": self._ibet_kvote(m),
            })
        return rezultat

    def _zapamti_igre(self, sajt, sport, nazivi):
        self.nepoznate_igre.setdefault((sajt, sport), set()).update(nazivi)

    # ---------- Admiral ----------
    def _admiral(self, sajt, sport):
        sada = datetime.now()
        url = ("https://srboffer.admiralbet.rs/api/offer/getWebEventsSelections?pageId=35"
               f"&sportId={SPORT_ID['admiral'][sport]}&isLive=false"
               f"&dateFrom={sada:%Y-%m-%dT%H:%M:%S}.000&dateTo=2031-01-01T00:00:00.000"
               "&eventMappingTypes=1&eventMappingTypes=2&eventMappingTypes=3"
               "&eventMappingTypes=4&eventMappingTypes=5")
        # bez ova dva zaglavlja Admiral vraca praznu listu
        r = self._get(sajt, sport, url, headers={**HEADERS, "Language": "sr-Latn", "OfficeId": "138"})
        if r is None:
            return None
        sada_ms = time.time() * 1000
        rezultat, nazivi = [], set()
        for e in r.json():
            ext = str(e.get("externalEventId") or "")
            if e.get("isLive") or not ext.startswith("sr:match:") or not e.get("isPlayable", True):
                continue
            pocetak = _ms(e["dateTime"] + "Z")  # Admiral salje UTC vreme bez oznake (provereno)
            if pocetak <= sada_ms:
                continue
            po_igri = {}
            for b in e.get("bets") or []:
                if b.get("sbv") or not b.get("isPlayable", True):
                    continue  # igre sa granicom (golovi...) jos ne poredimo
                ime = (b.get("betTypeName") or "").strip().lower()
                nazivi.add(ime)
                po_igri[ime] = {o["name"]: o["odd"] for o in b.get("betOutcomes") or []
                                if o.get("isPlayable", True) and o.get("odd")}
            domacin, gost = _dvoje(e.get("name", ""))
            rezultat.append({
                "sajt": sajt, "sport": sport, "br": ext[len("sr:match:"):],
                "domacin": domacin, "gost": gost, "liga": e.get("competitionName", ""),
                "pocetak_ms": pocetak, "kvote": _prevedi(po_igri),
            })
        self._zapamti_igre(sajt, sport, nazivi)
        return rezultat

    # ---------- Superbet ----------
    def _superbet(self, sajt, sport):
        od = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        do = od + timedelta(days=365)
        f = lambda d: quote(d.strftime("%Y-%m-%dT%H:%M:%S.000Z"), safe="")  # noqa: E731
        url = ("https://production-superbet-offer-rs.freetls.fastly.net/sb-rs/api/v3/subscription/"
               f"sr-Latn-RS/prematch?sports={SPORT_ID['superbet'][sport]}&startDate={f(od)}&endDate={f(do)}")
        r = self._get(sajt, sport, url, headers={**HEADERS, "Accept": "text/event-stream"}, stream=True)
        if r is None:
            return None
        # Ovo je "tok" koji se ne zavrsava: prva poruka je ceo snimak ponude, posle
        # stizu samo promene. Citamo prvu poruku i zatvaramo vezu.
        delovi, t0 = [], time.time()
        try:
            for linija in r.iter_lines(decode_unicode=True):
                if linija and linija.startswith("data:"):
                    delovi.append(linija[5:])
                elif linija == "" and delovi:
                    break
                if time.time() - t0 > SUPERBET_MAX_S:
                    break
        finally:
            r.close()

        sada_ms = time.time() * 1000
        rezultat, nazivi = [], set()
        for deo in delovi:
            for e in json.loads(deo):
                fx = e.get("fixture") or {}
                br = fx.get("betradar_id")
                if not br or not fx.get("utc_date"):
                    continue
                pocetak = _ms(fx["utc_date"])
                if pocetak <= sada_ms:
                    continue
                po_igri = {}
                for m in e.get("markets") or []:
                    ime = (m.get("name") or "").strip().lower()
                    nazivi.add(ime)
                    ishodi = {}
                    for o in m.get("odds") or []:
                        md = o.get("metadata") or {}
                        if o.get("status") == 1 and o.get("price") and not md.get("specifiers"):
                            ishodi[md.get("name")] = o["price"]
                    po_igri[ime] = ishodi
                domacin, gost = _dvoje((fx.get("event_name") or "").replace("·", " - "))
                rezultat.append({
                    "sajt": sajt, "sport": sport, "br": str(br),
                    "domacin": domacin, "gost": gost, "liga": "",
                    "pocetak_ms": pocetak, "kvote": _prevedi(po_igri),
                })
        self._zapamti_igre(sajt, sport, nazivi)
        return rezultat

    # ---------- Balkanbet (NSoft) ----------
    # NSoft igre imaju samo broj. Brojevi su provereni poredjenjem sa kolonama na sajtu
    # (2026-11-04). Uz to se proveravaju i nazivi ishoda, pa pogresan broj ne moze da prodje.
    BB_KONACAN = {6: "S", 141: "H", 93: "HB",          # konacan ishod 1/X/2
                  1955: "T", 84: "V", 2060: "TT"}      # pobednik 1/2 (P1/P2)
    BB_DUPLA = {368: "S", 147: "H"}                     # 1X/12/X2
    def _balkanbet(self, sajt, sport):
        jezik = "sr-Latn"
        params = {
            "deliveryPlatformId": "3",
            "dataFormat": json.dumps({"default": "object", "events": "array", "outcomes": "array"}),
            "language": json.dumps({"default": jezik, "events": jezik, "sport": jezik, "category": jezik,
                                    "tournament": jezik, "team": jezik, "market": jezik}),
            "timezone": "Europe/Belgrade",
            "company": "{}",
            "companyUuid": BALKANBET_FIRMA,
            "filter[sportId]": str(SPORT_ID["balkanbet"][sport]),
            "filter[from]": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "sort": "categoryPosition,categoryName,tournamentPosition,tournamentName,startsAt",
            "offerTemplate": "WEB_OVERVIEW",
            "shortProps": "1",
        }
        r = self._get(sajt, sport, "https://sports-sm-distribution-api.de-2.nsoftcdn.com/api/v1/events",
                      params=params, headers=HEADERS)
        if r is None:
            return None
        d = r.json()["data"]
        mp = d["_mapping"]
        E, M, O = mp["event"], mp["market"], mp["outcome"]
        sada_ms = time.time() * 1000
        rezultat, nazivi = [], set()
        for e in d.get("events") or []:
            br = e.get(E["rootEventId"])
            if not br or e.get(E["active"]) not in (1, True):
                continue
            pocetak = _ms(e[E["startsAt"]])
            if pocetak <= sada_ms:
                continue
            po_igri = {}
            for m in (e.get(E["markets"]) or {}).values():
                if m.get(M["active"]) not in (1, True) or m.get(M["specialValues"]):
                    continue
                ishodi = {{"P1": "1", "P2": "2"}.get(o.get(O["name"]), o.get(O["name"])): o.get(O["odd"])
                          for o in m.get(M["outcomes"]) or [] if o.get(O["active"]) in (1, True)}
                mid = m.get(M["marketId"])
                nazivi.add(f"{mid}:{'/'.join(map(str, ishodi))}")
                if self.BB_KONACAN.get(mid) == sport:
                    po_igri["konacan ishod"] = ishodi
                elif self.BB_DUPLA.get(mid) == sport:
                    po_igri["dupla sansa"] = ishodi
            domacin, gost = _dvoje(e.get(E["name"]) or "")
            rezultat.append({
                "sajt": sajt, "sport": sport, "br": str(br),
                "domacin": domacin, "gost": gost, "liga": e.get(E["tournamentName"]) or "",
                "pocetak_ms": pocetak, "kvote": _prevedi(po_igri),
            })
        self._zapamti_igre(sajt, sport, nazivi)
        return rezultat
