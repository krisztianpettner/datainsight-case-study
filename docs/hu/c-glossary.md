[English](../en/c-glossary.md) · **Magyar** · [↑ README](../../README.hu.md)

# Szójegyzék

| fogalom | jelentése itt |
|---|---|
| **Pedro** | persona: kisvállalkozó, aki feltölti a számláit és fizet. Piackutatásból megszemélyesítve, nem valódi személy. |
| **Maria** | persona: a könyvelője, aki ingyen használja a szolgáltatást és lezárja a hónapot. Piackutatásból megszemélyesítve, nem valódi személy. |
| **pilot-konfiguráció** | az első valódi felhasználókra előkészített beállítás — mindenekelőtt kikapcsolt automatikus jóváhagyással. **Pilot-felhasználó nem volt:** a megkeresés nem hozott ügyfelet, így a „pilot" itt soha nem jelent élő ügyféladatot. |
| **operátor** | a szolgáltatás oldalán dolgozó belső szerep, egy főre tervezve, helyettessel: az ellenőrző pultnál átnézi a számlákat, felügyeli a rendszert, figyeli a félautomata ügyfélszolgálatot, és meghívja a könyvelőket a platformra. Nem a könyvelő. |
| **NIF** | portugál adóazonosító szám (9 jegy, ellenőrzőszámmal). |
| **ATCUD** | az az egyedi kód, amelyet minden portugál számla hordoz, és az adóhatóságnál regisztrált. |
| **AT QR-kód** | az aláírt QR-kód a portugál számlákon; hordozza a kibocsátó és a vevő NIF-jét, a dátumot, a sorszámot, az ATCUD-ot, az ÁFA-t és a végösszegeket. |
| **orákulum** | független forrás, amit a motornak nem kell bizalomra elfogadnia — itt az AT QR-kód. |
| **e-Fatura** | a portugál rendszer, amelyen át a számlák fejléce és ÁFA-ja az államhoz kerül — tételsorok nélkül. |
| **VIES** | az EU-s szolgáltatás, amely igazolja, hogy egy közösségi adószám aktív-e; a fordított adózás bizonyítéka. |
| **fordított adózás** | határon átnyúló EU-s B2B szabály: az ÁFA-t a vevő számolja el, nem az eladó. |
| **tételsorok** | a számla egyes sorai — termék, mennyiség, egységár, ÁFA-kulcs. A nehéz rész. |
| **tier 1 / 2 / 3** | (1) a QR-tartalom · (2) sémák és heurisztikák a fejlécre, plusz a tételsor-létra · (3) helyi LLM, csak ha a létra semmit nem ad. |
| **létra** | a tételsor-kiolvasó rétegek sorrendje; az első réteg nyer, amelyik sort ad. |
| **master / delta séma** | országos szintű YAML / számlázóprogramonkénti YAML föléje. |
| **arany-halmaz** | 203 annotált, nyilvános mintaszámla a kiolvasás mérésére. |
| **tiszta részhalmaz** | az arany-halmaz 134 tisztán mérhető számlája — kimaradnak a nettó-végösszeg horgony nélküliek, a több számlát tartalmazó csomagok és a nem-számlák. |
| **HITL** | human in the loop: ember nézi át, amit a gép nem tudott igazolni. Itt: az **ellenőrző pult**. |
| **fő mérőszám** (north-star) | az az egy szám, amire egy szakaszt kormányzunk — itt az operátor számlánkénti perce. |
| **vetület** | olvasásra szánt másolat arról, amit a felhasználók láthatnak, a nyilvános szerveren; az igazság a PC-n marad. |
| **bitre azonos lépcső** | blokkonkénti refaktor egy befagyasztott alapvonal mögött, minden lépésnél bizonyítva, hogy egyetlen kimenet sem változik. |
| **eltérés-lista** | számozott lista minden különbségről az éles telepítés és a dokumentumai között, mindegyik állapottal. |
| **pásztor-szerep** | az én szerepem az AI-ügynökök felé: irány, korlátok, kapuk, ellenőrzés, mérés — nem a kód gépelése. |
| **bizonyíték-törvény** | értékesítési lista-szabály: egy kitalált domain nem igazolhatja önmagát; független jel kell. |
| **on-prem** | saját hardveren, nem felhőben. |

## Az öt „kapu" — egy szó, öt különböző dolog

| kapu | mit dönt el | fejezet |
|---|---|---|
| **azonossági kapu** | mezőnként: egyezik-e két független forrás (zöld / borostyán / piros), és elég megbízható-e a dokumentum ahhoz, hogy kihagyja az ellenőrzést | [Bizalom](05-trust.md#az-azonossági-kapu--ahol-a-bizalomról-döntünk) |
| **mentési kapu** | az ellenőrző pulton: ugyanazok a validátorok ítélik meg, amit az operátor beír | [Bizalom](05-trust.md#az-ellenőrző-pult) |
| **PII-kapu** | ügyfélszámla tartalma nem kerül LLM elé, a fejlesztő ügynökök elé sem | [Biztonság](07-security-and-isolation.md#adatvédelem-az-építő-felé-is) |
| **napindító kapu** | nincs kódmódosítás, commit vagy küldés, amíg a session nyitó rutinja le nem futott | [Munkamód](13-how-i-worked.md) |
| **kilépési kapu** (piacra lépés) | mikor hagyjuk el az egyik értékesítési csatornát a következőért | [Piacra lépés](11-go-to-market.md#piacra-lépés-mint-mérőgép) |
