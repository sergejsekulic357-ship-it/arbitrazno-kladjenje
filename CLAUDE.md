# Arbitrazno kladjenje

Licna aplikacija (koristi je samo vlasnik): povlaci kvote sa domacih (srpskih) kladionica,
uporedjuje ih, nalazi arbitraze u svim sportovima i salje ih na Telegram.
Najbitnije je da aplikacija RADI. Jezik: Python 3.13.

---

## 1. Kako radimo zajedno (pravila korisnika)

- **Uvek odgovaraj na srpskom** (latinica), jednostavno i jasno.
- **Polako, korak po korak.** Redosled je uvek: predlog plana -> korisnik kaze "kreni" -> kod -> objasnjenje.
  NE pravi nista pre dogovora (jednom je cela aplikacija napravljena bez pitanja - to se ne ponavlja).
- **Objasni razmisljanje:** sta si uradio, kako, i ZASTO, u svakom koraku.
- Kad korisnik kaze da hoce nesto **sam da uradi** (npr. git komande) - daj samo korake, ne izvrsavaj.
- Kad korisnik trazi preporuku - **daj jasnu preporuku**, ne samo listu opcija.
- Korisnik **sam proverava kvote na sajtu** i javlja greske; tada popravljamo.
- Budi iskren o ogranicenjima (npr. arbitraza je retka, "0 nadjeno" je podatak, ne kvar).

## 2. Zahtevi i blokada IP adrese (NAJVAZNIJE)

Korisnik se boji da mu kladionice ne blokiraju IP adresu.
- **Pre svakog novog talasa zahteva reci koliko zahteva i ka kojim sajtovima, pa sacekaj "ok".**
- Analizu radi nad **vec sacuvanim fajlovima**, ne salji iste zahteve ponovo.
- Pauza izmedju zahteva (>= 2 s u aplikaciji, 5 s pri istrazivanju).
- Interval pracenja: **danju 5 min, nocu (01-07h) 15 min**; smanjivati samo uz dogovor.
- Rucno "Osvezi" najcesce na 2 min.
- Na 403/429 **odmah stani** za taj sajt (aplikacija pravi pauzu 30 min) i javi korisniku.
- **Nikakvo zaobilazenje zastita:** bez rotacije IP, proxy-ja, resavanja Cloudflare/captcha.
  Sajtovi sa takvom zastitom se ostavljaju ili se trazi normalan nacin preko Chrome-a.

## 3. Pravila arbitraze

- **Samo utakmice pre pocetka.** Live je iskljucen (kvote skacu, tiketi se zakljucavaju). Mozda kasnije.
- **U `igre.py` ulaze SAMO igre cije je znacenje provereno.** Lazna arbitraza = pravi gubitak novca.
- Statisticko trazenje parova pravi lazne parove (dve kvote ~1.85 izgledaju kao par) -
  nova igra se dodaje tek kad se naziv potvrdi na sajtu.
- Igre sa granicom (golovi/poeni/hendikep) ne porediti dok se ne proveri da je granica ista.
- Utakmice se uparuju po **`brMatchId`** (Betradar ID), ne po imenu.
- Faza testiranja: **belezi SVAKU arbitrazu**, ma koliko mala, uz trajanje.
- Kombinovati vise igara i sportova (1X2, 1 vs X2, X vs 12, 2 vs 1X, pobednik...) - vise sansi.
- Ulozi se zaokruzuju (kladionice ne vole 347.83), profit se racuna posle zaokruzivanja.
- U porukama uvek podsetnik: "pre uplate proveri kvote na sajtu".

## 4. Podela posla

- **Aplikacija** radi ceo dan dok je terminal otvoren (povlaci, racuna, belezi).
  Bez automatskog pokretanja sa Windows-om - korisnik to NE zeli.
- **Telegram salje SAMO:** novu arbitrazu (odmah, u bilo koje doba), jutarnji izvestaj u 07:00
  (sa SVEZIM kvotama) i upozorenje ako kladionica odbije zahtev (403/429).
  "Nestala", "pokrenuto" i slicno ide samo u zapisnik.
- **Claude** pravi i popravlja aplikaciju i analizira `podaci/arbitraze.jsonl` posle testa.
  Claude NE radi nocu sam; ideja sa Grok botom koji naredjuje Claude-u je odbacena (skupo, nepouzdano, nepotrebno).
- **Korisnik** proverava kvote na sajtu i odlucuje sta igra.

## 5. Git i tajne

- Korisnik sam radi commit/push. Claude ne commit-uje i ne push-uje bez izricitog zahteva.
- Na git idu **samo bitni fajlovi** (kod, `static/`, `README.md`, `CLAUDE.md`, `.env.example`,
  `requirements.txt`, `.gitignore`). NE idu: `.env`, `podaci/`, `__pycache__/`, logovi, IDE fajlovi.
- **Tokeni (Telegram) nikad u kod, chat ili git** - samo u `.env`.
- Git identitet: `sergej.sekulic357@gmail.com`; GitHub nalog `sergejsekulic357-ship-it`
  (NE `segi357-lgtm`). Repo: github.com/sergejsekulic357-ship-it/arbitrazno-kladjenje
- Projekat je namerno van OneDrive-a (`C:\Users\segi3\projekti\`).
- Ako `python` otvara Microsoft Store: terminal je star -> otvori nov ili osvezi PATH.

---

## 6. Tehnicki deo

### Pokretanje
`python app.py` -> stranica http://127.0.0.1:5000 + pozadinsko pracenje + Telegram.
Telegram se podesava jednom: `python telegram_podesi.py`. Podesavanja: `.env` (sablon `.env.example`).
Zapis arbitraza: `podaci/arbitraze.jsonl` (dogadjaji: nova / nestala / jutarnji_izvestaj).

### Fajlovi
- `kladionice.py` - citanje kvota, pauze, kaznena pauza posle 403/429
- `igre.py` - samo proverene grupe igara (kodovi -> nazivi)
- `pretraga.py` - uparivanje po brMatchId + trazenje arbitraze (+ "skoro" do 2%)
- `arbitraza.py` - matematika (zbir 1/kvota, raspodela uloga sa zaokruzivanjem)
- `pracenje.py` - zivotni vek arbitraza, log, Telegram, jutarnji izvestaj
- `telegram.py`, `telegram_podesi.py` - slanje poruka / jednokratno podesavanje
- `app.py` - Flask server + pozadinska petlja; `static/index.html` - UI (arbitraze, sve kvote, kalkulator)

### Kladionice (stanje 2026-11-04, spisak licenciranih: uis.gov.rs/rsc/spisakpnaziv)
| Kladionica | Stanje |
|---|---|
| MaxBet, Soccer, MerkurXtip, Oktagon, Brazilbet, Betole, 365.rs | rade - isti softver ("ibet"), jedan citac, svi sportovi |
| Admiral, Superbet, Balkanbet | rade - svi sportovi osim kosarke, samo konacan ishod/pobednik (+ dupla sansa gde postoji). Nazivi provereni 2026-11-04 |
| Mozzart, Meridian | zastita (Cloudflare / token sesije) - NE zaobilaziti. U aplikaciji su "proveri rucno" |
| Ambassador + Tasbet (Evona API) | API radi (zaglavlja `TerminalId: 1`, `LanguageId: srl`, `Device-Type: desktop`; najvise 100 meceva po zahtevu), ALI Betradar ID ima samo ~4% meceva (sopstveni izvor "ExeFeed") -> bez uparivanja po imenu ne ide. Za sad "proveri rucno" |
| Volcano (xtreme.bet), Starbet, King | javno dostupni, jos nisu istrazeni do kraja |
| 1xBet, Betwinner, Vivatbet, bet365 | ne mogu se citati obicnim putem |
| Pinnbet | nije na spisku licenciranih; Lutrija nema sport; MrBit samo kazino |

API "ibet": `GET {sajt}/restapi/offer/sr/sport/{S|T|TT|H|HB|V|B}/mob?annex=0&desktopVersion=2.39.7&locale=sr`
(MaxBet: `annex=3&desktopVersion=1.2.1.10`). Jedan zahtev = ceo sport. Polje `esMatches`;
kvote u `odds` {kod: kvota}, kod Soccer-a `betMap[kod]["NULL"]["ov"]`. Iskljuciti `live`, `blocked`, zapocete.
Sportovi: S fudbal, B kosarka, T tenis, H hokej, HB rukomet, V odbojka, TT stoni tenis (ES, F prazni).
- Admiral: `srboffer.admiralbet.rs/api/offer/getWebEventsSelections` + zaglavlja `Language: sr-Latn`, `OfficeId: 138`
  (bez njih vraca []). Betradar u `externalEventId` "sr:match:N" (samo ~pola meceva). `dateTime` je UTC bez "Z".
- Superbet: `production-superbet-offer-rs.freetls.fastly.net/.../subscription/sr-Latn-RS/prematch` je TOK (SSE) -
  cita se prva poruka (ceo snimak) pa se veza zatvara. Datumi zaokruzeni na sat, inace 400.
- Balkanbet (NSoft): `sports-sm-distribution-api.de-2.nsoftcdn.com/api/v1/events`, skraceni kljucevi (`_mapping`),
  `rootEventId` = Betradar (provereno: 684/702 poklapanja). Igre su brojevi (proverene na sajtu): 1X2 = 6 (S), 141 (H),
  93 (HB); pobednik = 1955 (T), 84 (V, ishodi P1/P2), 2060 (TT); dupla sansa = 368 (S), 147 (H).
- Admiral nazivi: "Konacan ishod", "Pobednik", "Dupla sansa"; NE "Pobednik (+OT+Pen)" ni "1.set - Pobednik".
- Isti Betradar ID sa razlicitim vremenom pocetka (>30 min) se izbacuje iz poredjenja (`pretraga._isto_vreme`).

### Kodovi igara (isti na sva 4 sajta)
Potvrdjeno: 1/2/3 = 1/X/2 (bez neresenog: 1 i 3 = pobednik); 7=1X, 8=12, 9=X2.
Nepotvrdjeno: 22, 24, 2xx, 5xxxx... Kosarka jos nije ukljucena (nema proverenih igara).

### Nalazi iz analize
- Ove 4 kladionice cesto imaju **identicne kvote** (isti dobavljac) -> arbitraza retka.
  Prvi snimak: 1821 kombinacija, 0 arbitraza, najbliza -0.74% (Arsenal - Hull, 1X2).
- Zajednickih utakmica pre pocetka: ~700 fudbal, ~110 stoni tenis, ~25 tenis, desetine ostalo.

## 7. Sledeci koraci
1. Pustiti aplikaciju sa 10 kladionica i analizirati `podaci/arbitraze.jsonl` i `podaci/ciklusi.jsonl`.
2. Odluka: uparivanje po imenu+vremenu za Ambassador/Tasbet (drugi izvor kvota = vise sansi, ali rizik laznih parova)?
3. Istraziti Volcano, Starbet, King (imaju li Betradar ID).
4. Potvrditi nazive ostalih igara (golovi sa granicom - Admiral ih jasno imenuje, GG/NG, hendikep, kosarka) i dodati u `igre.py`.
5. Nov izgled stranice za pocetnike (predlog dat, ceka "kreni").
