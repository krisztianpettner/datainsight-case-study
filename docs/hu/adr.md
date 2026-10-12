[English](../en/adr.md) · **Magyar** · [↑ README](../../README.hu.md) · [Áttekintés](00-at-a-glance.md)

# Architektúra-döntési rekordok

Tizennégy döntés, amely a rendszert formálta, rögzített formában: **kontextus · döntés · elvetett
alternatívák · következmények · állapot**. A sorszámok az [Áttekintés](00-at-a-glance.md) sorszámai.

---

### ADR-01 — Nincs felhős feldolgozás

- **Kontextus.** Az ügyfelek kisvállalkozók és a könyvelőik; az adat a beszállítóik, áraik és
  árréseik. A bizalom maga a termék.
- **Döntés.** A nyers számla kizárólag a saját hardveremen dolgozódik fel; külső AI-szolgáltatás
  soha nem látja az ügyféladatot. Nyilvános szerver továbbíthat és státuszt mutathat, feldolgozni soha.
- **Elvetve.** Felhős OCR/LLM API-k (jobb pontosság, nincs hardver) — hamissá tennék az alapígéretet.
- **Következmények.** Három gép, tunnelek, helyi OCR és egy kis helyi modell; egyetlen helyi
  feldolgozó gép; fix költségek, amelyek csak volumennel amortizálódnak.
- **Állapot.** A teljes projekt alatt tartva. → [Infrastruktúra](04-infrastructure.md)

### ADR-02 — Az adóhatósági QR-kód az orákulum

- **Kontextus.** Egy modell saját megbízhatósági pontszáma nem hitelesítheti a kimenetét.
- **Döntés.** Portugál számlánál az aláírt QR-tartalom a fejléc-értékek igazságforrása; a vizuális olvasat keresztellenőrzés.
- **Elvetve.** Kizárólag a kiolvasási megbízhatóságban bízni.
- **Következmények.** Gépileg ellenőrizhető bizalom az arany-halmaz ~79 %-án; QR nélküli számlánál nincs orákulum.
- **Állapot.** Tartva. → [Kiolvasó motor](02-parsing-engine.md)

### ADR-03 — Rétegzett kiolvasás, a helyi modell az utolsó

- **Döntés.** QR → séma és heurisztika → táblázat-kiolvasó létra → helyi LLM csak akkor, ha minden más üres.
- **Elvetve.** LLM-első kiolvasás (helyi hardveren lassú, nem ellenőrizhető).
- **Következmények.** Több kódút, amit konzisztensen kell tartani; minden kimeneti sor rögzíti, melyik módszer adta.
- **Állapot.** Tartva.

### ADR-04 — A séma adat

- **Döntés.** Országonként egy master YAML, számlázó szoftverenként egy delta YAML, a QR-ban lévő
  szoftver-tanúsítványszám alapján választva, tartalékként a kibocsátó adószámával.
- **Elvetve.** Beszállítói logika Python-kódban.
- **Következmények.** Egy új elrendezés egy YAML-fájl; a lefedettség szoftverenként nő. Egy
  tervezett elrendezés-ujjlenyomat tartalék megépült, de soha nem lett bekötve.
- **Állapot.** Tartva.

### ADR-05 — Precizitás először: soha nem találgatunk

- **Döntés.** Ha egy érték nem olvasható biztosan, nem állítjuk elő; a mező ellenőrzésre megy.
- **Elvetve.** Legjobb igyekezet szerinti kimenet alacsony megbízhatósági jelzéssel.
- **Következmények.** Szándékosan alacsonyabb automatizálási arány. A hiányzó értéket elkapjuk; a
  magabiztosan rossz eljut a könyvelőhöz.
- **Állapot.** Tartva.

### ADR-06 — Mezőnkénti megbízhatósági kapu, előbb szigorúan

- **Döntés.** Minden mezőt aszerint sorolunk be, hogyan igazolható (független forrás / aritmetika
  / semmi), és zöld–borostyán–piros sávba tesszük; a dokumentum annyira megbízható, mint a
  leggyengébb kritikus mezője. A pilotra az automatikus jóváhagyás kódban ki volt kapcsolva;
  lazítás csak mért bizonyíték alapján, mezőnként.
- **Elvetve.** Egyetlen dokumentum-szintű küszöb.
- **Következmények.** A pilot alatt az ellenőrző pult vitte az összes számlát; a fő mérőszám az
  operátor-perc számlánként lett.
- **Állapot.** Tartva; soha nem lazítottuk — a pilot nem hozta meg a bizonyítékot.

### ADR-07 — Két alkalmazás a nyilvános szerveren

- **Döntés.** Egy vékony edge app (feltöltés, push, levél-webhookok) és egy portál app (a felhasználók adatai), külön függőségekkel.
- **Elvetve.** Egyetlen API-alkalmazás.
- **Következmények.** A feltört edge nem éri el az ügyfél-logikát; két telepítendő egység.
- **Állapot.** Tartva. (A fizetési webhook végül a portál appba került, ahol az adatbázisa él — dokumentálva.)

### ADR-08 — Három adatbázis mint három csomópont

- **Döntés.** Az edge DB és a portál DB a nyilvános szerveren, a feldolgozási DB — az igazság
  forrása — a PC-n; a nyilvános oldal maszkolt vetületet tart.
- **Elvetve.** Egyetlen, a nyilvános szerverről is elérhető közös adatbázis.
- **Következmények.** A nyilvános szerver elveszhet anélkül, hogy az igazság elveszne vagy
  kiszivárogna; egy hidat meg kellett tervezni; a rossz adatbázisra futó javítás nulla sorral „sikerül".
- **Állapot.** Tartva.

### ADR-09 — Rétegzett kapcsolatok, a feldolgozó telephelyről semmi nem látszik

- **Döntés.** Cloudflare a nyilvános szerver előtt, Tailscale közte és a NAS között, belül LAN.
- **Kivezetve.** Egy külön WireGuard-tunnel — előbb megépült, aztán redundánsként kivezettem (a Tailscale maga is WireGuard).
- **Következmények.** Nulla nyitott TCP-port a feldolgozó telephelyen, kívülről mérve (2026. szept.); bármely kapcsolat kiesése
  megállítja a folyamot — vészút: SSH-lehúzás.
- **Állapot.** Tartva.

### ADR-10 — A vállalkozó fizet, a könyvelő nem — és jutalékot sem kap

- **Döntés.** A vállalkozó az egyetlen fizető; a könyvelő ingyen használja a szolgáltatást, és meghívja az ügyfeleit.
- **Elvetve.** A könyvelő fizessen; a könyvelő kapjon ajánlói jutalékot.
- **Miért nincs jutalék.** A könyvelő az ügyfele bizalmi tanácsadója és a kimenetünk bírája; ha
  pénzt kapna azért, hogy minket ajánljon, összeférhetetlenbe kerülne — ez etikátlanná tenné a rendszert.
- **Következmények.** Két felhasználói csoport, két felület, egyirányú meghívási folyamat hozzájárulási rekordokkal.
- **Állapot.** Tartva.

### ADR-11 — Sávos, használat-alapú árazás

- **Kontextus.** A fix csomagok kredit-felhalmozási csapdát szültek: a fel nem használt kredit lemondáshoz vezetett.
- **Döntés.** €39 platformdíj + sávos, számlánkénti ár (€1,75 → €1,45).
- **Elvetve.** Fix csomagok; tiszta használat-alapú; önválasztott sávok.
- **Következmények.** Igazságos a kis ügyfeleknek, kevésbé kiszámítható bevétel; a későbbi
  összehasonlítás megmutatta, hogy a dokumentumonkénti ár csak ember által ellenőrzött eredményre indokolt.
- **Állapot.** Megvalósítva; a sávos havi csomag nyitott ötlet maradt.

### ADR-12 — A PII-kapu az építőre is vonatkozik

- **Döntés.** Ügyfélszámla tartalma soha nem kerül LLM elé — a rendszert fejlesztő AI-ügynökök elé
  sem. A hibakeresés és a séma-tanítás karakterazonos pszeudonimizált adaton vagy érték nélküli ujjlenyomaton fut.
- **Elvetve.** „Csak most az egyszer, a hibakereséshez."
- **Előzmény.** Ügyfélszámla soha nem került modell elé: élő ügyféladat nem volt, a fejlesztési korpusz önkéntesen megosztott, nyilvános minta volt. A kaput 2026 júliusában tettem gépiessé (eszköz-hook).
- **Következmények.** Egy pszeudonimizáló motor és egy maszkolt adaton futó tanítási rutin; lassabb hibakeresés.
- **Állapot.** Tartva.

### ADR-13 — A pénz útja felelősség szerint szétválasztva

- **Döntés.** A Stripe beszedi a fizetést; a saját adatbázisunkban egy csak-hozzáírható főkönyv
  dönti el, mennyi a tartozás; egy havi CSV egy helyi számlázó programot táplál a hivatalos
  számlához; a kifizetés egy EUR-számlára megy.
- **Elvetve.** Stripe-számlázás (a kibocsátó magyar cég); online számlázó szolgáltatások; a Stripe
  használat-mérője mint igazságforrás.
- **Következmények.** A számlázási igazság a saját adatbázisunkban, auditálhatóan marad; négy rendszert kell
  egyeztetni; a fordított adózást kódban, VIES-bizonyítékkal kényszerítjük ki.
- **Állapot.** A CSV-ig megépült; a számlázási visszaút terv maradt. → [Számlázás](04c-billing.md)

### ADR-14 — A pipeline-híd mappa-szerződés, nem API

- **Kontextus.** A feldolgozó gép soha nem lehet elérhető az internetről, a feltöltés viszont egy nyilvános szerverre érkezik.
- **Döntés.** A nyilvános szerver minden feltöltést SSH-n (Tailscale-en belül) egy ügyfelenkénti outbox-mappába streamel a NAS-on. A PC-n egy figyelő felveszi a fájlt, feldolgozza, és a státuszt visszaküldi a portálnak. A PC-t soha senki nem hívja.
- **Elvetve.** A PC által kiszolgált sor vagy HTTP API (bejövő végpont a telephelyre); feldolgozás a nyilvános szerveren.
- **Következmények.** Nincs nyitott port és nyilvános végpont a feldolgozó telephelyen; minden hibamódnak meghatározott kimenete van — stabilitás-várakozás, jelzőfájlok a dupla feldolgozás ellen, idempotens upsert összeomlás után, duplikátum-kapu, legjobb igyekezet szerinti státusz-küldés, a döntés a státusz előtt mentődik. Ára: lekérdezési késleltetés és jelzőfájl-könyvelés.
- **Állapot.** Tartva. → [Az adat útja](03-data-path.md#a-híd--hogyan-hibázik-biztonságosan)
