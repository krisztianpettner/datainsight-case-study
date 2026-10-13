[English](../en/12-post-mortem.md) · **Magyar** · [↑ README](../../README.hu.md)

# Post-mortem

> **Egy mondatban:** az igény valós volt, és a fejléc-kiolvasás működött — de túl későn kezdtem
> értékesíteni, egyetlen ki nem próbált csatornán, egy olyan technikai maggal, amely a legnehezebb részt még nem oldotta meg.

## Mi történt

| mikor | mi |
|---|---|
| 2025. okt. – 2026. márc. | Motor és első platform: rétegzett kiolvasás, sémák, validációs szabályok. ~270 commit e hat hónapban. |
| 2026. ápr. – máj. | A platform kiépítése: kétoldalú portál, számlázás, telepítés-refaktor, biztonság. Csúcs: 320 commit májusban. |
| 2026. máj. | A tételsorok első őszinte mérése (a labor-kiolvasón): a mérhető számlák **19 %-a** egyezett teljesen. |
| 2026. jún. – júl. | Emberi ellenőrző pult, azonossági kapu, adat-izoláció; a megkeresési gépezet felépítése. |
| 2026. júl. – aug. | A megkeresés indulása: hideg e-mail portugál könyvelőirodáknak. ~240 levél, **0 emberi válasz**. |
| 2026. aug. | Második mérés nagyobb arany-halmazon: **10,3 %** egyezés (a mért számlákon); a tiszta részhalmazon a számlák **57 %-ából** egyáltalán nem jött tételsor. |
| 2026. szept. | A piac újraolvasása: a „hiányzó számlák" lista már létezik a vezető könyvelőprogramban. |
| 2026. okt. | A projekt lezárva. |

## Miért bukott el — három ok, súly szerint

### 1. Az igény valós volt — a vevőhöz eljutás volt a gond

Az igényt nem találgattuk. Piackutatás és józan ész diktálta: a portugál könyvelők szakmai testületének elnöke ([forrás](b-metrics.md#források))
számokban mondta ki — *a könyvelő idejének 20–30 %-a a dokumentumok utáni szaladgálással megy el*.
A kisvállalkozók 2026 végéig még sima PDF-számlát állíthatnak ki, a külföldi számlák pedig
egyáltalán nem jelennek meg az állami e-számla-adatban.

Ami nem működött: **eljutni a könyvelőkhöz, és megszerezni a figyelmüket.** Az értékesítés csak
akkor indult, amikor a termék már elkészült, lényegében egyetlen csatornán — hideg e-mailen. Addigra az egész tét egy soha ki nem próbált csatornán múlt.

### 2. A technikai mag nem érte el azt a szintet, amit az ígéret igényelt

A portugál számla fejléce már eljut az adóhatósághoz — a könyvelő enélkül is megkapja. Az érték a
**tételsorokban** volt, és ez az a probléma, amit a teljes dokumentum-AI iparág sem oldott meg
megbízhatóan. A méréseim ezt korán megmondták (19 % májusban, 10,3 % augusztusban egy nehezebb
halmazon — a jelölt labor-kiolvasón mérve, nem a produkciós létrán), és én a precizitást választottam a lefedettség helyett: soha ne találgass, küldd
ellenőrzésre. A bizalom szempontjából ez helyes volt — de így az emberi pult vitte a munka
zömét, és a „csendes" automatizálás soha nem érkezett meg.

### 3. A sarok zsúfoltabb volt, mint amilyennek látszott

A nagy dokumentum-AI szállítók a nagyvállalati piac felé mentek, a kis könyvelők sarka szabadnak
tűnt. Csakhogy a könyvelők saját szoftverei folyamatosan hozzáadták ugyanennek az ígéretnek a
darabjait — szeptemberben derült ki, hogy a „hiányzó számlák" lista már létezik a vezető portugál
könyvelőprogramban, annak havi €9-os csomagjában ([forrás](b-metrics.md#források)). Egy új belépőnek a megmaradt részben kell egyértelműen jobbnak
lennie, és az a rész a tételsor volt.

### A megkeresési számokról

~240 levél, nulla válasz — ez nem ítélet. 120 kézbesített első megkeresésnél és 1 %-os valós
válaszaránynál a nulla válasz nagyjából az esetek 30 %-ában előfordul. Ami *mérhetően* rossz volt:
5,5 %-os visszapattanás, ~250 szavas levelek ott, ahol 20–100 működik, és egy-két érintés, miközben
a válaszok zöme a második–hatodik érintésből jön. A csatornát soha nem teszteltük akkora méretben,
amelyen tisztán el tudott volna bukni.

## Mit csinálnék másképp

1. **Az első hónapban elkezdeni értékesíteni, az építéssel párhuzamosan.** Két-három csatornát
   korán és kicsiben kipróbálni, hogy az építés azt kövesse, amit a piac válaszol.
2. **Először a nehéz problémát mérni.** A tételsor-arány volt maga az üzlet, és csak a platform
   felépülése után mértem meg. Ennek kellett volna az első kísérletnek lennie.
3. **Olyan piacot választani, amit belülről ismerek — vagy keresni egy valódi embert, aki ismeri.**
   Valakit, aki rálát a könyvelők mindennapi munkájára, és ki tudja nyitni az első ajtókat.
4. **Kisebb, eladható első szeletet szállítani** — azt a részt, ami már működik —, és a többit a
   fizető felhasználók után építeni.
5. **Az architekturális fegyelmet megtartani — nem az volt a probléma.** A kényszerek, a
   döntésnapló és a mérési szokás tették lehetővé, hogy a kudarc tisztán látható legyen.

## Mit adott nekem

> *Nem lett élő. De élmény volt megépíteni — és miközben építettem, én is épültem.*

- Egy rendszer végponttól végpontig tervezése kemény kényszerek mellett: adat-szuverenitás,
  ügyfél-izoláció, bizalom.
- Egy egyéves, egyszemélyes projekt vezetése AI-ügynökcsapattal — és megtanulni, hol
  kell az embernek tartania a vonalat: irány, kényszerek, kapuk, review, mérés.
- Kimondani: „ez a mérés nemet mond" — és eszerint cselekedni.
