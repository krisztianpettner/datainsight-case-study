[English](../en/08-metrics.md) · **Magyar** · [↑ README](../../README.hu.md)

# Mérőszámok

> Minden számnak van dátuma és forrása. Ahol egy szám szűkebb dolgot mér, mint amilyennek
> hangzik, a tábla kimondja.

## A munka mérete

| mérőszám | érték | mérve |
|---|---|---|
| commitok | 1 564 | git-történet, 2025. okt. → 2026. szept. |
| Python | ~249 000 sor 1 149 fájlban | követett fájlok, 2026-10-12 |
| ebből teszt | ~75 000 sor 365 fájlban; 3 690 tesztfüggvény | ugyanott |
| frontend | ~28 000 sor 177 fájlban | ugyanott, az elavult app nélkül |
| Docker-szolgáltatások | 18 | `docker-compose.yml` |
| kiolvasási sémák | 2 országos master + 1 általános master + 19 szoftver-delta (YAML) | `schemas/` |
| architektúra-dokumentumok | 70 | `docs/architecture/` |
| session-naplók | 182 | 2026. febr. → szept. |
| döntés- és tanulság-jegyzetek | ~300 | memória-rendszer |

```mermaid
xychart-beta
    title "Commitok havonta"
    x-axis [okt, nov, dec, jan, febr, márc, ápr, máj, jún, júl, aug, szept]
    y-axis "commit" 0 --> 350
    bar [46, 56, 17, 35, 52, 63, 145, 320, 215, 212, 195, 208]
```

Hová ment a munka — az egyes területeket érintő commitok (egy commit több területet is érinthet):
platform ~580 · kiolvasó motor és labor ~270 · tesztek és QA ~270 · felhasználói felületek ~230 ·
piac, árazás, jog, landing ~70 (e munka zöme tervezési jegyzetekben él, nem commitokban).

## A motor

| mérőszám | érték | dátum | mit mér valójában |
|---|---|---|---|
| arany-halmaz | 203 annotált számla | 2026. aug. | nyilvános mintaszámlák, nem ügyféladat |
| teljesen egyező tételsor | **19 %** (59 mérhető) | 2026. máj. | a **labor-kiolvasó** (táblázat-felismerő modell), nem a produkciós létra |
| teljesen egyező tételsor | **10,3 %** (203-ból 101 mérve, a futás leállítva) | 2026. aug. | ugyanaz a labor-kiolvasó, nagyobb és nehezebb halmazon |
| tételsort egyáltalán nem adó számlák | a tiszta részhalmaz 57 %-a | 2026. aug. | ugyanaz |
| a magabiztos sáv precizitása | 0,854 | 2026. máj. | labor-kapu a mérhető halmazon |
| QR-kód nélküli számlák | az arany-halmaz 21 %-a | 2026. aug. | független orákulum nélküli hányad |
| medián feldolgozási idő | 132 mp dokumentumonként | 2026. aug. | labor-futás, a táblázat-modellel együtt |
| refaktor-biztonság | 10 / 10 arany-számla bitre azonos előtte és utána | 2026. máj. | portugál pipeline-alapvonal |
| automatikus jóváhagyás élesben | **kikapcsolva** — minden számla ellenőrzésre | pilot | szándékos beállítás, nem mérés |

## A platform

| mérőszám | érték | dátum |
|---|---|---|
| közvetlenül adatbázishoz nyúló route-fájlok | 70-ből 55 | 2026-10-12 (regex-számlálás) |
| a jogosultság-feloldó átállása | 14 karakterizációs + 3 differenciál-teszt, 0 regresszió | 2026. jún. |
| telepítési drift-lista | 24 tétel, a zöme egy nap alatt lezárva 7 fázisban | 2026. máj. |

## Infrastruktúra

| mérőszám | érték | dátum |
|---|---|---|
| nyitott TCP-portok a feldolgozó telephelyen, a VPS-ről szkennelve (100 leggyakoribb TCP-port, SYN, 3,5 mp késleltetés) | 0 | 2026-09-11 |
| a port-szkennelési csapda reakcióideje | < 20 mp | 2026. szept. |
| néma mentési hiba, mielőtt észrevettük | 17 nap, 412 sehová nem továbbított hibajelzés | 2026. ápr.–máj. |
| telephelyen kívüli git-pillanatkép | teljes történet, ellenőrzött bundle, minden munkanap után | 2026. júl.-tól |

## A piac

| mérőszám | érték | dátum |
|---|---|---|
| minősített könyvelőiroda-címek | 149 | 2026. aug. |
| első megkeresés elküldve / kézbesítve | 127 / 120 | 2026. aug. |
| visszapattanási arány | 5,5 % (viszonyítás: ≤ 2 %) | 2026. aug. |
| levelek összesen, utókövetéssel | ~240 | 2026. aug. |
| emberi válasz | 0 | 2026. aug. |
| 0 válasz esélye 1 %-os valós aránynál és 120 kézbesítésnél | ~30 % | — túl kicsi minta az ítélethez |
| valódi fizetés | 0 — a Stripe éles módban, a pilot nem jutott el a számlázásig | 2026. szept. |

## A mérési tanulságok

- **Nézd meg, mit mér a szám.** A tételsor-arányok egy jelölt kiolvasót mértek, nem a produkciós
  utat — ezt későn vettem észre.
- **A nullának saját bizonyíték kell.** A port-szkennelés két tisztának látszó nullája a módszer
  mellékterméke volt; a receptet kijavítottam, mielőtt az eredményben megbíztam.
- **A jelzés, amit senki nem kap meg, nem jelzés.** 412 hibajelzés, riasztási csatorna nélkül.
- **A kísérletet a döntéshez kell méretezni.** 120 kézbesítés nem tud különbséget tenni 1 % és 0 % válaszarány között.

## Források

| | állítás | forrás |
|---|---|---|
| S1 | „a szakember idejének 20–30 %-a a dokumentumok utáni szaladgálással megy el" | Interjú a Portugál Okleveles Könyvelők Rendjének (OCC) elnökével (*bastonária*), *Revista Contabilista* 307, 2025. dec. — [occ.pt](https://www.occ.pt/pt-pt/noticias/entrevista-paula-franco-bastonaria-da-occ) |
| S2 | az ügyfelek utáni szaladgálás súrlódása | ECO, 2025. dec. 10. — [eco.sapo.pt](https://eco.sapo.pt/2025/12/10/occ-quer-alteracao-legislativa-para-criar-o-contabilista-3-0/) |
| S3 | az e-Fatura adat soha nem tartalmazza az áru vagy szolgáltatás leírását, a személyes adatok védelme miatt | Portal das Finanças, e-Fatura tájékoztató — [portaldasfinancas.gov.pt](https://info.portaldasfinancas.gov.pt/pt/apoio_contribuinte/Folhetos_informativos/Documents/efatura_portal.pdf) |
| S4 | „hiányzó dokumentumok bekérése e-mailben" a vezető könyvelőprogramban | TOConline kézikönyv — [manual.toconline.pt](https://manual.toconline.pt/support/solutions/articles/3000110064-pedir-documentos-em-falta-por-e-mail); csomagok havi €0 / €9 / €14,58, toconline.pt árlap |

Mind 2026 szeptemberében megtekintve.
