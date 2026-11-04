"""Matematika arbitraze - nezavisno od toga odakle stizu kvote."""

from dataclasses import dataclass


@dataclass
class Ishod:
    naziv: str        # npr. "Arsenal", "Draw"
    kvota: float
    kladionica: str


@dataclass
class Arbitraza:
    utakmica: str
    pocetak: str
    ishodi: list[Ishod]
    zbir: float               # zbir 1/kvota
    ulozi: list[float]        # zaokruzeni ulozi po ishodu
    ukupan_ulog: float
    min_isplata: float        # najmanja isplata posle zaokruzivanja

    @property
    def profit(self):
        return self.min_isplata - self.ukupan_ulog

    @property
    def profit_procenat(self):
        return self.profit / self.ukupan_ulog * 100


def zbir_verovatnoca(kvote):
    return sum(1 / k for k in kvote)


def rasporedi_ulog(kvote, ukupan_ulog, zaokruzi_na=1.0):
    """
    Raspodela uloga tako da isplata bude (skoro) ista za svaki ishod.
    Ulozi se zaokruzuju (kladionice ne vole ulog 347.83), pa se vraca
    i najmanja stvarna isplata posle zaokruzivanja.
    """
    zbir = zbir_verovatnoca(kvote)
    ulozi = [round(ukupan_ulog / k / zbir / zaokruzi_na) * zaokruzi_na for k in kvote]
    ukupno = sum(ulozi)
    min_isplata = min(u * k for u, k in zip(ulozi, kvote))
    return ulozi, ukupno, min_isplata


def najbolje_kvote(kvote_po_kladionici):
    """
    kvote_po_kladionici: {kladionica: {ishod: kvota}}
    Vraca listu Ishod sa najboljom kvotom za svaki ishod.
    """
    najbolje = {}
    for kladionica, kvote in kvote_po_kladionici.items():
        for naziv, kvota in kvote.items():
            if naziv not in najbolje or kvota > najbolje[naziv].kvota:
                najbolje[naziv] = Ishod(naziv, kvota, kladionica)
    return list(najbolje.values())


def nadji_arbitrazu(utakmica, pocetak, kvote_po_kladionici, broj_ishoda,
                    ukupan_ulog, zaokruzi_na=1.0, min_profit_procenat=0.0):
    """Vraca Arbitraza ako postoji (i isplati se posle zaokruzivanja), inace None."""
    ishodi = najbolje_kvote(kvote_po_kladionici)
    if len(ishodi) != broj_ishoda:
        return None  # nedostaje neki ishod - ne moze se pokriti sve

    kvote = [i.kvota for i in ishodi]
    zbir = zbir_verovatnoca(kvote)
    if zbir >= 1:
        return None

    ulozi, ukupno, min_isplata = rasporedi_ulog(kvote, ukupan_ulog, zaokruzi_na)
    arb = Arbitraza(utakmica, pocetak, ishodi, zbir, ulozi, ukupno, min_isplata)
    if arb.profit_procenat < min_profit_procenat or arb.profit <= 0:
        return None
    return arb
