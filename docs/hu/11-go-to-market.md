[English](../en/11-go-to-market.md) · **Magyar** · [↑ README](../../README.hu.md)

# Piacra lépés és árazás

> **Egy mondatban:** az árazás csomagokból sávos mérésig jutott, az értékesítés pedig előre rögzített
> küszöbökkel dolgozó mérőgépként épült fel — amely sosem kapott elég adatot a döntéshez.
>
> *Hogy miért mozdult az érték-tézis, és mire szolgált a termék, az [A probléma és a piac](01-problem-and-market.md) fejezetben van.*

## Árazás — csomagokból sávos mérésig

**A csapda.** Az első modell fix csomagokat árult (havi €175 / €495 / €1 500 a 100 / 300 / 1 000
számlára). Egy árazási szimuláció (2026 március, még egyetlen ügyfél előtt) megmutatta a csapdát: az
ügyfelek ritkán használják el pontosan a keretet, a kredit felhalmozódik, és aki fel nem használt
krediten ül, megkérdezi: „minek fizessek ebben a hónapban?" — beépített ok a lemondásra. *A termék
saját maga ellen dolgozott volna.*

**Négy modellt vetettünk össze:** fix csomag · tiszta használat-alapú · hibrid választott sávval
· hibrid automatikus, progresszív sávokkal. **A választott: €39 platformdíj + sávos használat** —
1–60 számla €1,75, 61–120 €1,65, 121–300 €1,55, 301+ €1,45. Az ár magától csökken, ahogy nő a
volumen; semmi nincs előre kifizetve, semmi nem vész el. A számított optimum €49 volt; a €39
bevezető árként jelent meg.

**A későbbi összehasonlítás** dokumentumonkénti árakat vetett össze: a tiszta kiolvasó eszközök a
miénk töredékéért dolgoznak. A következtetés: nem a kiolvasás árában versenyzünk — **az
ember által ellenőrzött eredményt adjuk el**, nem az olvasást. A sávos havi csomag volt a következő
ötlet; nyitva maradt.

## A könyvelő × vállalkozó kombináció

- **Bevétel = könyvelők × ügyfél/könyvelő × számla/ügyfél × ár.** A kar az első kettő: egy
  könyvelő megnyerése, és a teljes ügyfélkörének tömeges meghívása. A számlák száma kimenet, nem kar.
- **Közel nulla ügyfélszerzési költség** a könyvelői csatornán — ezt az utat járták az inkumbensek is.
- **A könyvelő mint társ-szolgáltató:** a vállalkozó és a hatóságok között áll; mi mindkettejük
  infrastruktúrája vagyunk. Ő ingyen használja; kizárólag a vállalkozó fizet.

## Unit-economics — minek kellett igaznak lennie

- **Kivétel-alapú ellenőrzés, nem teljes:** a modell automatikusan elfogadja, amit igazolni tud;
  a többit ember intézi. Havi ~200 számla alatt a hibrid ember-gép megoldás nyer; ~500 felett az
  automatizálás. A kis ügyfeleink (havi 12–70) a hibrid zónában vannak.
- **A fő mérőszám az első naptól: emberi perc számlánként az időben.** Ha a volumennel csökken, a
  modell skálázódik; ha lapos marad, a haszon munkadíj-haszon.
- **A hardver fix költség:** felhő nélkül a feldolgozó gép a volumennel amortizálódik. Egy GPU-s
  gép helyi kép-nyelvi modellekhez tervben volt — a bevételből finanszírozva, nem előtte.
- **Egy második piac mint opció:** az USA-ban nincs e-számla rendszer, így ott a kiolvasás
  megtartja a teljes értékét — de a felhő nélküli megkülönböztetés nem utazik vele. „Később
  mutálódni", nem pivot.

## Piacra lépés mint mérőgép

- **Csatornatérkép** — hideg e-mail, utókövetés, fórumok, könyvelőprogram-partnerek, a szakmai
  testület, tartalom, fizetett —, **kilépési kapukkal ellátott hullámokban** nyitva, nem dátumok
  szerint: egy csatornán maradunk, amíg fizetőt nem hoz, vagy a válaszaránya 150 megkeresés után
  bizonyíthatóan 1 % alatt nincs.
- **Listaépítés bizonyíték-törvénnyel:** egy kitalált domain nem igazolhatja önmagát — független
  jel kell (a cégjegyzékszám az oldalon, a szakmai nyilvántartás bejegyzése).
- **Népszámlálás, nem mintavétel;** minden arányhoz konfidencia-intervallum; **a döntési
  küszöbök leírva, mielőtt az adatot megnéznénk;** visszapattanási kapu minden küldés előtt.
- Eredmény: ~240 levél, emberi válasz nélkül — az alatt a méret alatt, amelyen a csatorna tisztán
  el tudott volna bukni. → [Post-mortem](12-post-mortem.md)

## A jogi réteg

Az indulásra elkészült tervezetek, az ügyfél felé szólók portugálul is: adatfeldolgozási szerződés
könyvelői kiegészítéssel, felhasználási feltételek, adatvédelmi és süti-szabályzat, elfogadható
használat, hozzájárulás-kezelés, fióktörlési protokoll, alvállalkozói lista, megőrzési összesítő,
adatkezelési nyilvántartás, két hatásvizsgálat (profilozás; törlés és átadás), jogos érdek
mérlegelések (profilozás; hideg megkeresés), incidenskezelési terv, titoktartási megállapodások.

## Megmentendő ötletek

1. **A hiányzó-számla lista mint mag**, az ügyfél saját előzményeiből előre jelezve — a
   könyvelő meglepetését a hónap utánról a hónap közbenre hozza.
2. **„A hónap lezárva érkezik"** — szolgáltatás-definíció, nem szoftverfunkció.
3. **A könyvelő mint célzási mechanizmus** egy kívülről láthatatlan belépési ponthoz.
4. **Sávos mérés** csomagok helyett — nincs kredit-csapda.
5. **Bizonyíték-törvény az értékesítési listákra**, és az adat előtt rögzített döntési küszöbök.
