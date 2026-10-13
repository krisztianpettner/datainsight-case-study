[English](README.md) · **Magyar**

# Dat[AI]nsight — egy számla-feldolgozó platform, megépítve és lezárva

**[Krisztián Pettner](https://github.com/krisztianpettner)** · rendszerarchitekt · [LinkedIn](https://www.linkedin.com/in/krisztian-pettner/)

> Felhő nélküli dokumentum-feldolgozó szolgáltatás portugál kisvállalkozásoknak és könyvelőiknek.
> Egy ember, nagyjából egy év munka, 1 564 commit. A motor, a platform és az ügyfél-felület
> megépült és telepítve volt, pilotra készen; a fejléc-kiolvasás működött, a tételsorok nem érték el
> a szükséges szintet, és a pilot nem kapta meg az első felhasználóját. Ez a repó annak a lenyomata,
> **hogyan és miért így terveztem** — nem termék.

## 30 másodpercben

**Az ötlet.** A kisvállalkozó (*Pedro*) feltölti a beszállítói számláit. A rendszer kiolvassa,
ellenőrzi, és strukturáltan átadja a könyvelőjének (*Mariának*), aki lezárja a hónapot.
Pedro fizet (havi €39 + számlánkénti díj); Maria ingyen használja, és hozza az ügyfeleit.
*Pedro és Maria piackutatásból megszemélyesített personák, nem valódi emberek.*

**A kemény kényszerek, amelyek mindent formáltak:**

| kényszer | következménye az architektúrában |
|---|---|
| **Nincs felhő** — a számlát csak saját hardveren dolgozzuk fel, nincs külső AI | a kiolvasás, az OCR és egy helyi LLM egy helyi PC-n fut; a nyilvános szerver számlát tárolás nélkül továbbít ([mi lépi át melyik határt](docs/hu/06-data-path.md#mi-lépi-át-melyik-határt)) |
| **Szigorú ügyfél-izoláció** — az egyik ügyfél soha nem látja a másik ügyfél adatait | minden végpont mögött egyetlen jogosultság-feloldó; a nyilvános oldalon csak maszkolt vetület |
| **A bizalom előbbre való az automatizálásnál** — a könyvelőhöz eljutó rossz érték helyrehozhatatlan | mezőnkénti azonossági kapu: automatikus jóváhagyás csak arra, amit független forrás igazol, minden más emberi ellenőrzésre megy |
| **Egy ember** | én terveztem az architektúrát; egy AI-ügynökcsapat e terv szerint írta a kódot; én tartottam a kényszereket, a kapukat, a review-t és a mérést |

**Miből áll:** a portugál adóhatóság QR-kódjához horgonyzott, rétegzett PDF-kiolvasó motor; egy
azonossági kapu, amely minden számlát automatikus jóváhagyásra vagy emberi ellenőrző pultra
irányít; kétoldalú termék teljes ügyfél-felülettel (vállalkozó + könyvelő); egy három gépen átívelő
pipeline-híd (nyilvános szerver → NAS → helyi PC) titkosított kapcsolatokkal; és a pénz útja a
kártyás fizetéstől egy csak-hozzáírható főkönyvig.

**Hogyan ért véget.** Az igény valós volt, de az értékesítés későn és egyetlen csatornán indult: a
hideg e-mail 127 könyvelőirodát ért el (~240 levél utókövetéssel együtt), emberi válasz nem jött.
A számlák **tételsorai** pedig — amire a könyvelőnek valójában szüksége van — nagyrészt emberi
ellenőrzésen maradtak. 2026 októberében lezártam a projektet. → [Post-mortem](docs/hu/12-post-mortem.md)

## Egy állítás ellenőrzése két perc alatt

Az azonossági kapu — az a rész, amely eldönti, mely értékekben lehet megbízni — önállóan fut:

```bash
python -m venv .venv && .venv/bin/pip install pytest
PYTHONPATH=src .venv/bin/python -m pytest tests/parsing/identity -q
# 51 passed   (2026-10-12)
```

## A fejezetek

Kevés az idő? Olvasd el a [00](docs/hu/00-at-a-glance.md)-t és a [12](docs/hu/12-post-mortem.md)-t — tizenöt perc.

| # | fejezet | mire felel | kód |
|---|---|---|---|
| 00 | [Áttekintés](docs/hu/00-at-a-glance.md) | az egész rendszer egy képen, és a tizennégy döntés soronként egy mondatban | |
| 01 | [A probléma és a piac](docs/hu/01-problem-and-market.md) | miért a tételsor, és nem a fejléc — és hogyan mozdult az érték-tézis | |
| 02 | [Termék és felhasználók](docs/hu/02-product-and-users.md) | ki fizet, ki hozza az ügyfeleket, hogyan kapcsolódnak | |
| 03 | [Az ügyfél-felület](docs/hu/03-client-interface.md) | mit látott ténylegesen a vállalkozó és a könyvelő, képernyőről képernyőre | |
| 04 | [Kiolvasó motor](docs/hu/04-parsing-engine.md) | hogyan lesz egy PDF-ből strukturált adat | [`src/parsing`](src/parsing), [`src/ingress`](src/ingress) |
| 05 | [Bizalom](docs/hu/05-trust.md) | mely értékekben lehet megbízni, mit lát az emberi ellenőr, hogyan mértük a pontosságot | [`src/parsing/identity`](src/parsing/identity) |
| 06 | [Adatút](docs/hu/06-data-path.md) | merre utazik egy számla három gépen át, és hogyan hibázik biztonságosan a híd | [`src/dispatch_watcher.py`](src/dispatch_watcher.py) |
| 07 | [Biztonság és izoláció](docs/hu/07-security-and-isolation.md) | ügyfél-izoláció, ki mit láthat, adatvédelem az MI-építő felé, a határ szkennelése | [`src/services/authz`](src/services/authz) |
| 08 | [Infrastruktúra és üzemeltetés](docs/hu/08-infrastructure.md) | a három csomópont és a négy kapcsolat, telepítés, mentés, monitorozás | |
| 09 | [Platform](docs/hu/09-platform.md) | a rétegzési szabály, és hogyan javítottuk lépcsőnként az eltérést | |
| 10 | [Számlázás](docs/hu/10-billing.md) | fizetés → főkönyv → szabályos számla | [`src/services`](src/services) |
| 11 | [Piacra lépés és árazás](docs/hu/11-go-to-market.md) | árazás, egységgazdaságtan, az értékesítés mint mérőgép | |
| 12 | [Post-mortem](docs/hu/12-post-mortem.md) | miért bukott el, és mit csinálnék másképp | |
| 13 | [Munkamód](docs/hu/13-how-i-worked.md) | mit döntöttem el én, és hogyan vezettem egy AI-ügynökcsapatot | |
| A | [Döntés-rekordok](docs/hu/a-decision-records.md) | a tizennégy döntés teljes egészében | |
| B | [Mérőszámok](docs/hu/b-metrics.md) | minden szám, dátummal és forrással | |
| C | [Szójegyzék](docs/hu/c-glossary.md) | az itt használt fogalmak | |

A [`src/`](src/README.md) kódja egy kb. negyven fájlos válogatott kivonat, olvasásra, nem futtatásra.

## A számok

| | |
|---|---|
| Időtartam | 2025. okt. → 2026. szept.; a munka zöme 2026 márciusától |
| Commitok | 1 564 (csúcs: 320 2026 májusában) |
| Python | ~249 ezer sor, ebből ~75 ezer teszt (3 690 tesztfüggvény) |
| Frontend | ~28 ezer sor — az ügyfél-webapp (40 képernyő), belső eszközök; plusz egy Flutter-app és egy Streamlit operátori konzol |
| Futtatókörnyezet | 18 Docker-szolgáltatás · 3 adatbázis · 22 YAML kiolvasási séma |
| Tervezési nyilvántartás | 70 architektúra-dokumentum · 182 session-napló · ~300 döntés/tanulság-jegyzet |

---

*A repó kódját AI-ügynökök (Claude) írták az én tervem szerint. Az architektúra az enyém —
mindenekelőtt a három gépen átívelő pipeline-híd, a nyilvános továbbítótól a NAS-átadáson és a
helyi feldolgozáson át a maszkolt státuszig. Az enyém a kényszerek, a döntések és azok
nyilvántartása is.*

<sub>© 2026 Krisztián Pettner. Megtekintésre megosztva; minden jog fenntartva.</sub>
