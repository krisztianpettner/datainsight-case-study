[English](../en/13-how-i-worked.md) · **Magyar** · [↑ README](../../README.hu.md)

# Hogyan dolgoztam — a pásztor szerepe

> **Egy mondatban:** a kódot AI-ügynökök írták; az én dolgom az volt, hogy eldöntsem, merre
> menjen, bekerítsem a terepet, és minden nap, bizonyíték alapján ellenőrizzem, hogy oda ment-e.

## A munkamegosztás

| ki | mit csinált |
|---|---|
| **AI-ügynökök** (Claude: egy vezető modell, egy kódoló modell, gyors felderítő modellek) | megírták a kódot, a teszteket és a dokumentumok zömét; átkutatták a kódbázist; terveket vázoltak; átnézték egymás munkáját |
| **én** | megterveztem az architektúrát — mindenekelőtt a három gépen átívelő pipeline-hidat; kijelöltem a nap célját, azokat a kényszereket, amelyek soha nem sérülhetnek, és a kapukat, amelyeken minden változásnak át kellett mennie; döntöttem; olvastam a bizonyítékot; nemet mondtam |

A 249 000 sort az ügynökök gépelték be. A terv, amit megvalósítanak, az enyém, és mindegyikért én
felelek — ezt a szerepet dokumentálja ez a repó.

## Amit én döntöttem el

| döntés | hol él |
|---|---|
| a három gépen átívelő pipeline-híd: nyilvános továbbító → NAS-átadás → helyi feldolgozás → maszkolt státusz vissza, bejövő API nélkül a PC felé | [Az adat útja](06-data-path.md#a-híd--hogyan-hibázik-biztonságosan), ADR-14 |
| az adóhatósági QR-kód mint orákulum, és a *soha ne találgass* — a hiányzó érték jobb, mint a rossz | [Kiolvasó motor](04-parsing-engine.md), ADR-02, ADR-05 |
| mezőnkénti azonossági kapu, előbb szigorúan, lazítás csak mért bizonyíték alapján | `src/parsing/identity/`, ADR-06 |
| a vállalkozó fizet, a könyvelő ingyen használja, és jutalékot sem kap | [Termék és felhasználók](02-product-and-users.md), ADR-10 |
| refaktor csak bitre azonos alapvonal mögött; „terv vs megépült" minden fejezetben | [Platform](09-platform.md), minden fejezet |
| a PII-kapu a rendszert építő AI-ra is vonatkozik | ADR-12 |

## Az öt dolog, amit a pásztor tart

| | mit jelentett a gyakorlatban |
|---|---|
| **Irány** | Minden session egy *fő fókusszal* (a stratégiai cél) és egy *al-fókusszal* (a mai feladat) indult, plusz azzal, amihez ma nem szabad nyúlni, és hogy mit jelent a „kész". Minden változást mindkettőhöz mértünk. |
| **Kényszerek** | Írott alkotmány: nincs felhős feldolgozás, a vállalkozó fizet és a könyvelő nem, zéró tolerancia az ügyfél-izolációban, pilot először. Plusz kódszabályok: hibajavítás miatt soha nem törlünk funkciót, soha nem gyengítünk tesztet, hogy átmenjen, romboló adatbázis-művelet csak kifejezett megerősítéssel. |
| **Kapuk** | Gépies ellenőrzőpontok a jó szándék helyett — lásd lent. |
| **Review** | Egy *devils-advocate* ügynök a terveket kódolás előtt, a változásokat commit előtt vizsgálta; egy *szerződés-ellenőrző* ügynök a frontend-hívásokat vetette össze a backend-végpontokkal; egy *jogi* ügynök mindent átnézett, ami személyes adatot érintett. |
| **Mérés** | Az állításból csak mérés után lett tény — és magát a mérést is auditáltuk (lásd [Mérőszámok](b-metrics.md)). |

## Kapuk — az eszköz kényszeríti ki, nem az emlékezet

Az emlékezésen múló fegyelem elkopik. Ezért a legfontosabb szabályok az eszközökbe költöztek:

- **A napindító kapu.** Egy hook blokkolt minden kódmódosítást, minden commitot és minden kimenő
  küldést, amíg a nyitó rutin le nem futott: az aktuális állapot, a friss commitok, a tegnapi
  ajánlás, a memória-index állapota. A kapu pecsétből dönt, nem abból, hogy „elolvastam".
- **A PII-kapu.** Ügyfélszámla tartalma soha nem került modell elé — se bemásolva, se fájlként, se
  al-ügynökön át. A hibakeresés csak pszeudonimizált másolaton futott.
- **A rétegzési szabály az új route-okra,** devils-advocate review-val a tervezéskor és újra a commit előtt.
- **Commit előtti dokumentum-ellenőrzés:** minden tervdokumentumnak státusza, típusa, gazdája és felülvizsgálati dátuma van.
- **Felidézés a saját szavaimból.** Minden üzenetemnél egy hook ~300 döntés- és tanulság-jegyzet
  közül megkereste a relevánsakat, és az ügynök elé tette — *ellenőrizendő nyomként*, soha nem bizonyítékként.

## Memória — hogy semmit ne kelljen kétszer eldönteni

| réteg | mit tartott |
|---|---|
| állapot-fájlok | hol tartunk, mi függ — a fejétől olvasva, minden sessionben |
| itinerek | a holnapi terv, a végén egy „**ÉN AJÁNLOM**" szakasszal — a következő session ebből indul, nem kérdez újra |
| session-naplók | 182 dátumozott napló: döntések, fájlok, teszteredmények |
| döntés- és tanulság-jegyzetek | ~300: 116 tanulság arról, *hogyan dolgozzunk*, 149 projekt-tény, 34 hivatkozás |
| architektúra-dokumentumok | 70, mindegyik státusszal és felülvizsgálati dátummal |
| tudásbázis-indexek | generált térképek a dokumentumokról, a kódról és a tesztadatról, hogy az ügynök kikeressen, ne 1 000 fájlt olvasson |

## Skillek — ismétlődő eljárások, egyszer megírva

Kilenc projekt-skill tette az ismétlődő munkát rögzített lépésű, rögzített kimenetű eljárássá,
hogy a különböző napok eredményei összevethetők legyenek: az azonossági kapu változtatási
protokollja (minden változásnál lefuttatott arany-halmazzal), a kiolvasó motor nyolcfázisú
hibalabora, a funkció → adatmodell harmonizációs felmérés, egy portugál personákkal futó
„hidegindítás" QA, három megkeresési rutin (napi ellenőrzés, listaépítés, küldési nap), egy
code-review ellenőrzőlista és maga a fejlesztési munkafolyamat.

## Tanulságok az AI-ügynökök vezetéséről

Mindegyik írott szabály lett, mert előtte mindegyik került valamibe.

1. **Címkézd a fékedet.** Ha habozom, az oknak nevet kell adni: *mért* (van bizonyíték —
   megállunk), *hiány* (nem tudjuk — megyünk, és mérünk), vagy *szabály* (írott szabály —
   betartjuk, vagy tudatosan módosítjuk). A címke nélküli „legyünk óvatosak" nem hordoz információt.
2. **Az al-ügynök ítélete hipotézis.** A felderítők szövegre keresnek; nem tudják megkülönböztetni
   az élő kódot a halottól. Kétszer is „aktívnak" nyilvánítottak egy használaton kívüli utat. A
   leleteket a forráshoz mérjük.
3. **Előbb cáfolni, aztán javítani.** Minden lelethez leírni, mi cáfolná — és először azt keresni.
4. **A néma nulla hazudik.** A rossz adatbázisra futó lekérdezés nulla sort ad, és sikernek látszik.
   A rossz módszerű szkennelés nulla nyitott portot talál. A nullának saját bizonyíték kell.
5. **A félig bekötött halott.** A projekt legdrágább mintázata: egy funkció elkészül, de soha nem
   lesz végponttól végpontig bekötve — a tesztekben működik, élesben nincs.
6. **Az alulméretezett kísérlet nem negatív eredmény.** 120 kézbesített első megkeresés válasz nélkül azt mondja: „túl
   kicsi ahhoz, hogy kiderüljön", nem azt, hogy „rossz az üzenet".
7. **Előbb olvasni, aztán kódolni.** Egy érett rendszert úgy lehet a leggyorsabban eltörni, ha
   megváltoztatjuk, mielőtt elolvasnánk, mit csinál már most.

## Amit egy másik, AI-ügynököket vezető architectnek mondanék

- Írd le a kényszereket az első prompt előtt; az ügynökök arra optimalizálnak, amit kihagysz.
- Minden fontos szabályt költöztess kapuba. A figyelmed a csapat legszűkösebb erőforrása.
- Rögzítsd a *miértet*, ne csak a *mit* — az ügynökök felejtenek, és te is fogsz.
- Mérd a mérést.
