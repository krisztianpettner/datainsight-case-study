[English](../en/07-security-and-isolation.md) · **Magyar** · [↑ README](../../README.hu.md)

# Biztonság és izoláció

> **Egy mondatban:** az izolációt egyetlen pont kényszeríti ki és tesztek bizonyítják, az
> adatvédelem a rendszert építő MI felé is érvényes, és a határt kívülről megtámadtuk, mielőtt
> zártnak neveztük volna.

## Ügyfél-izoláció — egyetlen kikényszerítési pont

- **Egyetlen jogosultság-feloldó** válaszol minden „láthatja-e ez a felhasználó ennek az ügyfélnek
  az adatát?" kérdésre — nem a route-okban szétszórt szűrők.
- **A könyvelői hozzáférés = kapcsolat + hozzájárulás.** Maria csak akkor lát egy ügyfelet, ha a
  könyvelő–ügyfél kapcsolat létezik, és az ügyfél hozzájárult.
- **A blokkolt kísérlet bizonyíték.** Egy ügyfélhatáron átnyúló kérés 403-at kap, *és* blokkolt
  hozzáférési kísérletként naplózódik.
- **Karakterizációs tesztek alatt vezettük be:** 14 teszt rögzítette a régi viselkedést, és 3
  differenciál-orákulum teszt vetette össze a régi és az új választ — nulla regresszió az
  átállásnál. Az ügyfélhatáron átnyúló tesztek kifejezetten a könyvelői utakat célozzák
  (hozzáférés kapcsolattal, profilozás hozzájárulással).
- **Egy személy, egy identitás.** A felhasználók három adatbázisban léteznek; egy identitás-térkép
  köti egy személyhez egy identitást mindhárom között.
- **A nyitott pontokat rangsoroltuk, nem söpörtük le:** a hozzájárulás kemény kapu legyen, ne
  formalitás; hibás identitás-egyezésnél zárt hibázás; szerepkör-kényszer adatbázis-szinten — és az
  erre épülő adatbázis-híd addig blokkolva maradt, amíg ezekről döntés nem született.

## Ki mit láthat

| adat | hol él | ki láthatja |
|---|---|---|
| nyers PDF | NAS outbox → PC, a kiadás utáni 48 óráig | a pipeline; az operátor az ellenőrzés alatt |
| kiolvasott értékek | PC feldolgozási adatbázis | az operátor; a vállalkozó és a könyvelője az exportokon keresztül |
| döntés-rekord | PC feldolgozási adatbázis | értékek redaktálva — csak nevek, pontszámok, hash-ek |
| státusz | VPS portál-adatbázis (vetület) | a vállalkozó; a könyvelője, ha össze vannak kötve és hozzájárult |
| job-rekord | VPS edge-adatbázis | az edge app (feltöltési nyilvántartás) |

*Az operátor* a szolgáltatás oldalán dolgozó belső szerep — nem a könyvelő. Hogy az adat
fizikailag merre utazik, és melyik hálózati szakasz mit olvashat, az az [Adatút](06-data-path.md#mi-lépi-át-melyik-határt) fejezetben van.

## A határ — kimondva, aztán megmérve

Az elv: **alapból tiltás, csak engedélylista; a feldolgozó gépek soha nem érhetők el az
internetről.** Az API előtt az nginx külön rate limitet tart az általános forgalomra, a
hitelesítésre (5/perc) és a regisztrációra (10/perc).

Egy elv csak állítás, amíg valaki meg nem támadja. 2026. szeptember 11-én kívülről szkenneltem a
telephelyet (a VPS-ről, SYN-szkennelés a 100 leggyakoribb TCP-portra): **a feldolgozó telephelyen
nulla nyitott TCP-port**, az UDP némán eldobva, és a port-szkennelési csapda 20 másodpercen belül
elkapta a szkennelést. A VPS-en csak a webes portok és az SSH látszottak. Az első két szkennelés a
mérésről is tanított: mindkettő „tiszta nullát" adott rossz okból (a szkennelési mód mellékterméke,
illetve a csapda félreértett időablaka) — a receptet kijavítottam, mielőtt az eredményben megbíztam
volna.

## Adatvédelem az építő felé is

A rendszert AI-ügynökök építették, és a felhő nélküli ígéretnek rájuk is érvényesnek kellett
lennie. **Ügyfélszámla soha nem került modell elé:** a pilot-konfigurációban élő ügyféladat nem
volt, a fejlesztési korpusz önkéntesen megosztott, nyilvános mintaszámlákból állt, és 2026
júliusától egy eszköz-kapu gépiesen is kikényszerítette a szabályt.

Hibakereséshez és séma-tanításhoz egy **pszeudonimizáló motor** készült: HMAC-kulcsolt,
karakterenkénti átalakítás, amely megtartja a formátumot és a hosszt (egy adószám érvényesnek
látszó adószám marad), miközben az érték eltűnik. A QR-tartalom és a PDF-metaadat is maszkolódik,
és egy szivárgás-ellenőrzés összeveti a kimenetet a bemenettel, mielőtt bármi kikerülne. A kulcsot
(salt) a rendszer induláskor ellenőrzi; ha a szállított helyőrző mégis bent maradna, az erre épülő
profilozó csatorna kikapcsolja magát, ahelyett hogy kitalálható hash-eket adna ki.

## Integritás — csendben nem szerkeszthető audit-napló

Minden feldolgozási esemény egy eseménynaplóba kerül, ahol minden bejegyzés hordozza az előző
hash-ét. Öt szolgáltatás olvas belőle — státusz, audit-riport, audit-horgony, megsemmisítő
takarító, portál-vetület —, így mind ugyanazt a történetet mondják.

## Terv vs megépült — őszintén

| terv | megépült |
|---|---|
| Cloudflare elöl, az origin rejtve | a VPS originje közvetlenül, a Cloudflare tűzfalát megkerülve is elérhető volt — a külső szkennelés találta meg; közepesnek minősítve, a projekt lezárásakor nyitva maradt |
| a hash-lánc ütemezett ellenőrzése | az ellenőrzés létezik, ütemezve nincs |
| a hozzájárulás kemény kapuként, zárt hibázású identitás-ellenőrzés | rangsorolva és specifikálva; az erre váró hidat visszatartottuk |
