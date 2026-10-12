[English](README.md) · **Magyar**

# Dat[AI]nsight — egy számla-feldolgozó platform, megépítve és lezárva

**[Krisztián Pettner](https://github.com/krisztianpettner)** · rendszerarchitekt · [LinkedIn](https://www.linkedin.com/in/krisztian-pettner/)

> Felhő nélküli dokumentum-feldolgozó szolgáltatás portugál kisvállalkozásoknak és könyvelőiknek.
> Egy ember, 6+ hónap aktív munka, 1 564 commit. A motor és a platform pilot-konfigurációban futott;
> a fejléc-kiolvasás működött, a tételsorok nem érték el a szükséges szintet, és a vállalkozás nem
> indult be. Ez a repó annak a lenyomata, **hogyan és miért így terveztem** — nem termék.

## 30 másodpercben

**Az ötlet.** A kisvállalkozó (*Pedro*) feltölti a beszállítói számláit. A rendszer kiolvassa,
ellenőrzi, és strukturáltan átadja a könyvelőjének (*Mariának*), aki lezárja a hónapot.
Pedro fizet (havi €39 + számlánkénti díj); Maria ingyen használja, és hozza az ügyfeleit.
*Pedro és Maria piackutatásból megszemélyesített personák, nem valódi emberek.*

**A kemény kényszerek, amelyek mindent formáltak:**

| kényszer | következménye az architektúrában |
|---|---|
| **Nincs felhő** — a számlát csak saját hardveren dolgozzuk fel, nincs külső AI | a kiolvasás, az OCR és egy helyi LLM egy helyi PC-n fut; a nyilvános szerver számlát tárolás nélkül továbbít ([mi lépi át melyik határt](docs/hu/03-data-path.md#mi-lépi-át-melyik-határt)) |
| **Szigorú ügyfél-izoláció** — az egyik ügyfél soha nem látja a másik ügyfél adatait | minden végpont mögött egyetlen jogosultság-feloldó; a nyilvános oldalon csak maszkolt vetület |
| **A bizalom előbbre való az automatizálásnál** — a könyvelőhöz eljutó rossz érték helyrehozhatatlan | mezőnkénti azonossági kapu: automatikus jóváhagyás csak arra, amit független forrás igazol, minden más emberi ellenőrzésre megy |
| **Egy ember** | én terveztem az architektúrát; egy AI-ügynökcsapat e terv szerint írta a kódot; én tartottam a kényszereket, a kapukat, a review-t és a mérést |

**Miből áll:** a portugál adóhatóság QR-kódjához horgonyzott, rétegzett PDF-kiolvasó motor; egy
azonossági kapu, amely minden számlát automatikus jóváhagyásra vagy emberi ellenőrző pultra
irányít; kétoldalú termék (vállalkozó + könyvelő); egy három gépen átívelő pipeline-híd (nyilvános
szerver → NAS → helyi PC) titkosított kapcsolatokkal; és a pénz útja a kártyás fizetéstől egy
csak-hozzáírható főkönyvig.

**Hogyan ért véget.** A számlák **tételsorai** — amire a könyvelőnek valójában szüksége van —
nagyrészt emberi ellenőrzésen maradtak. A hideg megkeresés 127 könyvelőirodát ért el (~240 levél
utókövetéssel együtt), emberi válasz nem jött. 2026 októberében lezártam a projektet.
→ [Post-mortem](docs/hu/09-post-mortem.md)

## Egy állítás ellenőrzése két perc alatt

Az azonossági kapu — az a rész, amely eldönti, mely értékekben lehet megbízni — önállóan fut:

```bash
python -m venv .venv && .venv/bin/pip install pytest
PYTHONPATH=src .venv/bin/python -m pytest tests/parsing/identity -q
# 51 passed   (2026-10-12)
```

## Olvasási útvonalak

| idő | olvasd |
|---|---|
| **15 perc** | ez az oldal → [Áttekintés](docs/hu/00-at-a-glance.md) → [Post-mortem](docs/hu/09-post-mortem.md) |
| **45 perc** | + [Kiolvasó motor](docs/hu/02-parsing-engine.md), [Az adat útja](docs/hu/03-data-path.md), [Számlázás](docs/hu/04c-billing.md), [Mérőszámok](docs/hu/08-metrics.md) |
| **mélyfúrás** | [Döntés-rekordok](docs/hu/adr.md) → [Kód-térkép](src/README.md) → a tesztek |

Ismeretlen fogalom? → [Szójegyzék](docs/hu/glossary.md)

## A számok

| | |
|---|---|
| Időtartam | 2025 vége → 2026. szeptember — 6+ hónap aktív munka, nyári szünettel |
| Repó-történet | 2025. október → 2026. szeptember |
| Commitok | 1 564 (csúcs: 320 2026 májusában) |
| Python | ~249 000 sor, ebből ~75 000 teszt (3 690 tesztfüggvény) |
| Frontend | ~28 000 sor (React) — vállalkozói és könyvelői portál, belső eszközök; plusz egy Flutter-app és egy Streamlit operátori konzol |
| Futtatás | 18 Docker-szolgáltatás · 3 adatbázis · 22 YAML kiolvasási séma |
| Tervezési napló | 70 architektúra-dokumentum · 182 session-napló · ~300 döntés- és tanulság-jegyzet |

## Hol mit találsz

| ha arra vagy kíváncsi… | olvasd |
|---|---|
| mi ez, egy oldalon | [Áttekintés](docs/hu/00-at-a-glance.md) |
| miért bukott el, és mit tanultam | [Post-mortem](docs/hu/09-post-mortem.md) |
| hogyan lesz egy PDF-ből megbízható adat | [Kiolvasó motor](docs/hu/02-parsing-engine.md) |
| merre jár az adat, ki láthatja, mi lépi át melyik határt | [Az adat útja](docs/hu/03-data-path.md) |
| hogyan illeszkedik a három gép és a kapcsolatok | [Infrastruktúra](docs/hu/04-infrastructure.md) · [Platform](docs/hu/04b-platform.md) |
| hogyan mozgott a pénz: fizetés → főkönyv → számla | [Számlázás](docs/hu/04c-billing.md) |
| ki fizet, ki hozza az ügyfeleket, és miért | [Kétoldalú termék](docs/hu/05-two-sided-product.md) |
| hogyan fejlődött az érték-tézis és az árazás | [Piac és árazás](docs/hu/06-market-and-pricing.md) |
| mit döntöttem el én magam, és hogyan vezettem egy AI-ügynökcsapatot | [Munkamód](docs/hu/07-how-i-worked.md) |
| minden szám, dátummal és forrással | [Mérőszámok](docs/hu/08-metrics.md) |
| a tizennégy döntés teljes egészében | [Döntés-rekordok](docs/hu/adr.md) |
| a fejezetek mögötti kód | [Kód-térkép](src/README.md) — válogatott kivonat, ~40 fájl |

---

*A repó kódját AI-ügynökök (Claude) írták az én tervem szerint. Az architektúra az enyém —
mindenekelőtt a három gépen átívelő pipeline-híd, a nyilvános továbbítótól a NAS-átadáson és a
helyi feldolgozáson át a maszkolt státuszig. Az enyém a kényszerek, a döntések és azok
nyilvántartása is.*

<sub>© 2026 Krisztián Pettner. Megtekintésre megosztva; minden jog fenntartva.</sub>
