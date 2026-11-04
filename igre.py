"""
Grupe igara koje ZAJEDNO pokrivaju sve moguce ishode.
Arbitraza je moguca samo unutar jedne grupe.

U ovaj spisak ulaze SAMO igre ciju smo znacajnost proverili:
- 1X2 i dupla sansa (1X, 12, X2) - potvrdjeno iz podataka:
  zbir 1/kvota za "1" i "9" je uvek ~1.07, sto znaci da je 9 = X2, itd.
- pobednik u sportovima bez neresenog (kod 1 i 3).
Igre sa granicom (golovi, poeni, hendikep) NISU ukljucene dok ne proverimo
nazive na sajtu - pogresno uparivanje bi dalo laznu arbitrazu.
"""

SPORTOVI = {
    "S": "Fudbal",
    "T": "Tenis",
    "TT": "Stoni tenis",
    "H": "Hokej",
    "HB": "Rukomet",
    "V": "Odbojka",
}

_1X2 = {"id": "1X2", "naziv": "Konacan ishod (1X2)",
        "kodovi": ["1", "2", "3"], "ishodi": ["1", "X", "2"]}

GRUPE = {
    "S": [
        _1X2,
        {"id": "1-X2", "naziv": "1 protiv X2", "kodovi": ["1", "9"], "ishodi": ["1", "X2"]},
        {"id": "X-12", "naziv": "X protiv 12", "kodovi": ["2", "8"], "ishodi": ["X", "12"]},
        {"id": "2-1X", "naziv": "2 protiv 1X", "kodovi": ["3", "7"], "ishodi": ["2", "1X"]},
    ],
    "H": [dict(_1X2, naziv="Konacan ishod 1X2 (regularno vreme)")],
    "HB": [_1X2],
    "T": [{"id": "pob", "naziv": "Pobednik meca", "kodovi": ["1", "3"], "ishodi": ["1", "2"]}],
    "TT": [{"id": "pob", "naziv": "Pobednik meca", "kodovi": ["1", "3"], "ishodi": ["1", "2"]}],
    "V": [{"id": "pob", "naziv": "Pobednik meca", "kodovi": ["1", "3"], "ishodi": ["1", "2"]}],
}
