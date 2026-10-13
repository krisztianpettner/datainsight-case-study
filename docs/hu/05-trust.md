[English](../en/05-trust.md) · **Magyar** · [↑ README](../../README.hu.md)

# Bizalom — az azonossági kapu, az ellenőrző pult, a labor

> **Egy mondatban:** egyetlen érték sem jut el a könyvelőhöz pusztán a gép szavára — minden mezőt
> független forráshoz mérünk, minden mást ember lát, és minden pontossági állítást egy rögzített
> arany-halmazra mérünk.

## Az azonossági kapu — ahol a bizalomról döntünk

Minden mezőnek van egy bejegyzése a **mező-katalógusban**: kanonikus név, QR-slot, vizuális
slotok, típus, kritikus-e, és hogyan ellenőrizhető:

| osztály | mi igazolja | példa |
|---|---|---|
| **a** | független forrás (QR, ellenőrzőösszeg) | adószámok, végösszegek, dátum, ATCUD |
| **b** | aritmetika a mezők között | nettó + ÁFA = bruttó |
| **c** | semmi — csak olvasott | beszállító neve, szabad szöveg |

A motor mezőnként összeveti a QR-olvasatot a vizuálissal (összegeknél 2 cent tűréssel), és sávba sorolja:

- 🟢 **zöld** — a két független forrás egyezik;
- 🟠 **borostyán** — csak egy forrás van, vagy enyhe eltérés;
- 🔴 **piros** — kemény szabály sérült (vétó).

A dokumentum megbízhatósága a **kritikus, ellenőrizhető mezői közül a legkisebb** — egyetlen
kétes végösszeg elég a megállításhoz. Ha nincs ellenőrizhető kritikus mező, a megbízhatóság nulla.

**A pilot-konfigurációban az automatikus jóváhagyás kódban ki volt kapcsolva.** Minden számla az ellenőrző
pultra ment, és a kapu azt döntötte el, *mit kell az operátornak megnéznie*, nem azt, *hogy
megnézi-e valaki*. A terv: mezőnként lazítani, kizárólag mért bizonyíték alapján — előbb
szigorú, aztán csak ott lazítunk, ahol a mérés megengedi.

## Az ellenőrző pult

A pult belső eszköz a PC-n. *Az operátor* a szolgáltatás oldalán dolgozó szerep — nem a könyvelő,
aki csak az eredményt látja. A szolgáltatást **egy operátorra, helyettessel** terveztem: minden más
automatikus volt, és csak három dolog igényelt embert — ez az ellenőrzés, a rendszer felügyelete és
a félautomata ügyfélszolgálat (gépi fordítás és korábbi esetekből tanuló válaszok). A pult kockázati
sorrendben, mezőnként mutatja a teendőt:

- **a zöld mezőket átugorja** — a kurzor meg sem áll rajtuk;
- adószámnál és végösszegnél a beviteli cella **üresen indul**, így az operátor azt gépeli be,
  amit lát, nem a gép javaslatát hagyja jóvá (horgonyhatás elleni védelem);
- mentéskor **ugyanazok a validátorok ítélik meg az embert, mint a gépet** — a rossz félhez
  beírt adószámot a rendszer elutasítja, hacsak nincs kifejezett felülbírálás.

A fő mérőszám nem az automatikus jóváhagyási arány volt, hanem az **operátor-idő számlánként**:
amíg a bizalom épül, minden ellenőrzésre megy, tehát a kérdés az, milyen gyorsan.

## A mérő-labor

- **Arany-halmaz:** 203 annotált számla (nyilvánosan elérhető mintaszámlák, nem ügyféladat). A
  *tiszta részhalmaz* — 134 számla — kihagyja a nettó-végösszeg horgony nélkülieket, a több
  számlát tartalmazó csomagokat és a nem-számlákat.
- **QR-horgonyzott tételsor-mérőszám:** kiadják-e a kiolvasott sorok a számla nettó végösszegét?
  Minden számla *egyező*, *eltérő összegű* vagy *üres* eredménnyel zárul.
- **Nyolcfázisú javító ciklus** — tájékozódás, mérés, triázs, diagnózis, kísérlet, javítás,
  ellenőrzés, rögzítés —, ahol minden változtatás a mért hatása alapján marad vagy megy.
- ⚠️ **Mit mérnek a számok.** A repóban szereplő tételsor-arányokat (19 % májusban; 10,3 %
  augusztusban — 10 a 97 viszonyítási alappal rendelkező számlából, a futás leállításáig mért 101 közül) a **labor-kiolvasón** mértük — egy táblázat-felismerő modellen, amelyet a létra
  következő rétegének jelöltjeként értékeltünk —, nem a fenti produkciós létrán. Ezt az
  eltérést én magam vettem észre, későn; a mérési tanulságok között szerepel.

## Terv vs megépült — őszintén

| terv | megépült |
|---|---|
| automatikus jóváhagyás egy megbízhatósági küszöb felett | a pilot-konfigurációban kikapcsolva; kapcsoló mögött létezett egy opcionális „biztonságos jóváhagyás" út |
| a kapu mezőnkénti lazítása, mért bizonyíték alapján | a változtatási protokoll és az arany-halmaz-ellenőrzés létezett; a projekt lezárásáig egyetlen mező sem lazult |
