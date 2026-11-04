"""
Uparivanje utakmica izmedju kladionica i trazenje arbitraze.

Uparivanje: po 'brMatchId' (Betradar ID utakmice) - isti je na svim sajtovima,
pa ne zavisimo od toga kako koja kladionica pise ime tima.
"""

from collections import defaultdict

from arbitraza import zbir_verovatnoca
from igre import GRUPE, SPORTOVI
from kladionice import RUCNO, SAJTOVI

SKORO_PRAG = 1.02   # "skoro arbitraza" - za prikaz u aplikaciji
MAX_RAZLIKA_MIN = 30  # ako sajt ima drugo vreme pocetka za isti ID - ne verujemo mu


def _isto_vreme(po_sajtu):
    """
    Isti Betradar ID bi trebalo da znaci istu utakmicu, ali retko se desi da neki sajt
    ima drugacije vreme (odlozena utakmica, greska u ID-ju). Takav sajt izbacujemo
    iz poredjenja za tu utakmicu - bolje propustiti nego dobiti laznu arbitrazu.
    """
    vremena = sorted(u["pocetak_ms"] for u in po_sajtu.values())
    srednje = vremena[len(vremena) // 2]
    return {s: u for s, u in po_sajtu.items()
            if abs(u["pocetak_ms"] - srednje) <= MAX_RAZLIKA_MIN * 60_000}


def potrebne_kvote(ishodi, zbir):
    """
    Za svaki ishod: koliku kvotu treba naci (na nekoj drugoj kladionici) da bi
    ovo postala arbitraza, ako ostali ishodi ostanu isti.
    zbir - 1/k_i + 1/nova < 1  =>  nova > 1 / (1 - (zbir - 1/k_i))
    """
    out = []
    for i in ishodi:
        ostatak = zbir - 1 / i["kvota"]
        out.append(round(1 / (1 - ostatak), 2) if ostatak < 1 else None)
    return out


def uporedi(sve_utakmice):
    """
    sve_utakmice: lista recnika iz Citac.preuzmi (sa svih sajtova).
    Vraca (mecevi, arbitraze, skoro).
    """
    po_mecu = defaultdict(dict)
    for u in sve_utakmice:
        po_mecu[(u["sport"], u["br"])][u["sajt"]] = u

    mecevi, arbitraze, skoro = [], [], []

    for (sport, br), po_sajtu in po_mecu.items():
        if len(po_sajtu) < 2:
            continue  # utakmica postoji samo na jednoj kladionici
        po_sajtu = _isto_vreme(po_sajtu)
        if len(po_sajtu) < 2:
            continue
        prvi = po_sajtu.get("maxbet") or next(iter(po_sajtu.values()))
        mec = {
            "id": f"{sport}-{br}",
            "sport": sport,
            "sport_naziv": SPORTOVI.get(sport, sport),
            "naziv": f"{prvi['domacin']} - {prvi['gost']}",
            "liga": prvi["liga"],
            "pocetak_ms": prvi["pocetak_ms"],
            "sajtovi": sorted(po_sajtu),
            "igre": [],
        }

        for grupa in GRUPE.get(sport, []):
            ishodi = []
            for kod, ime in zip(grupa["kodovi"], grupa["ishodi"]):
                kvote = {s: u["kvote"][kod] for s, u in po_sajtu.items()
                         if u["kvote"].get(kod, 0) > 1}
                if not kvote:
                    break
                najbolji_sajt = max(kvote, key=kvote.get)
                ishodi.append({
                    "naziv": ime,
                    "kvote": kvote,
                    "najbolja": {"sajt": najbolji_sajt,
                                 "naziv_sajta": SAJTOVI[najbolji_sajt]["naziv"],
                                 "kvota": kvote[najbolji_sajt]},
                })
            else:
                zbir = zbir_verovatnoca([i["najbolja"]["kvota"] for i in ishodi])
                igra = {"id": grupa["id"], "naziv": grupa["naziv"], "ishodi": ishodi,
                        "zbir": round(zbir, 5), "profit_proc": round((1 / zbir - 1) * 100, 3)}
                mec["igre"].append(igra)

                if zbir < SKORO_PRAG:
                    zapis = {
                        "kljuc": f"{mec['id']}-{grupa['id']}",
                        "mec_id": mec["id"],
                        "sport_naziv": mec["sport_naziv"],
                        "naziv": mec["naziv"],
                        "liga": mec["liga"],
                        "pocetak_ms": mec["pocetak_ms"],
                        "igra": grupa["naziv"],
                        "ishodi": [{"naziv": i["naziv"], **i["najbolja"]} for i in ishodi],
                        "zbir": igra["zbir"],
                        "profit_proc": igra["profit_proc"],
                    }
                    if zbir >= 1:
                        # skoro arbitraza: koju kvotu treba naci i gde jos da se proveri
                        zapis["potrebno"] = potrebne_kvote(zapis["ishodi"], zbir)
                        zapis["proveri_jos"] = (
                            [{"naziv": r["naziv"], "url": r["url"], "zasto": r["zasto"]} for r in RUCNO] +
                            [{"naziv": SAJTOVI[s]["naziv"], "url": "", "zasto": "nema ovaj mec kod nas"}
                             for s in SAJTOVI if s not in po_sajtu])
                    (arbitraze if zbir < 1 else skoro).append(zapis)

        if mec["igre"]:
            mecevi.append(mec)

    mecevi.sort(key=lambda m: m["pocetak_ms"])
    arbitraze.sort(key=lambda a: -a["profit_proc"])
    skoro.sort(key=lambda a: a["zbir"])
    return mecevi, arbitraze, skoro
