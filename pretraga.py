"""
Uparivanje utakmica izmedju kladionica i trazenje arbitraze.

Uparivanje: po 'brMatchId' (Betradar ID utakmice) - isti je na svim sajtovima,
pa ne zavisimo od toga kako koja kladionica pise ime tima.
"""

from collections import defaultdict

from arbitraza import zbir_verovatnoca
from igre import GRUPE, SPORTOVI
from kladionice import SAJTOVI

SKORO_PRAG = 1.02   # "skoro arbitraza" - za prikaz u aplikaciji


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
                    (arbitraze if zbir < 1 else skoro).append(zapis)

        if mec["igre"]:
            mecevi.append(mec)

    mecevi.sort(key=lambda m: m["pocetak_ms"])
    arbitraze.sort(key=lambda a: -a["profit_proc"])
    skoro.sort(key=lambda a: a["zbir"])
    return mecevi, arbitraze, skoro
