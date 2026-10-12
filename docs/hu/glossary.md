[English](../en/glossary.md) · **Magyar** · [↑ README](../../README.hu.md)

# Szójegyzék

| fogalom | jelentése itt |
|---|---|
| **Pedro** | persona: kisvállalkozó, aki feltölti a számláit és fizet. Piackutatásból megszemélyesítve, nem valódi személy. |
| **Maria** | persona: a könyvelője, aki ingyen használja a szolgáltatást és lezárja a hónapot. Piackutatásból megszemélyesítve, nem valódi személy. |
| **NIF** | portugál adóazonosító szám (9 jegy, ellenőrzőszámmal). |
| **ATCUD** | az az egyedi kód, amelyet minden portugál számla hordoz, és az adóhatóságnál regisztrált. |
| **AT QR-kód** | az aláírt QR-kód a portugál számlákon; hordozza a kibocsátó és a vevő NIF-jét, a dátumot, a sorszámot, az ATCUD-ot, az ÁFA-t és a végösszegeket. Itt: az **orákulum**. |
| **e-Fatura** | a portugál rendszer, amelyen át a számlák fejléce és ÁFA-ja az államhoz kerül — tételsorok nélkül. |
| **VIES** | az EU-s szolgáltatás, amely igazolja, hogy egy közösségi adószám aktív-e; a fordított adózás bizonyítéka. |
| **fordított adózás** | határon átnyúló EU-s B2B szabály: az ÁFA-t a vevő számolja el, nem az eladó. |
| **tételsorok** | a számla egyes sorai — termék, mennyiség, egységár, ÁFA-kulcs. A nehéz rész. |
| **arany-halmaz** | 203 annotált mintaszámla a kiolvasás mérésére. |
| **HITL** | human in the loop: ember nézi át, amit a gép nem tudott igazolni. Itt: az **ellenőrző pult**. |
| **tier 1 / 2 / 3** | QR és sablonok / sémák és heurisztika / helyi LLM — ebben a sorrendben. |
| **master / delta séma** | országos szintű YAML / számlázóprogramonkénti YAML föléje. |
| **on-prem** | saját hardveren, nem felhőben. |

## Az öt „kapu" — egy szó, öt különböző dolog

| kapu | mit dönt el | fejezet |
|---|---|---|
| **azonossági kapu** | mezőnként: egyezik-e két független forrás (zöld / borostyán / piros), és elég megbízható-e a dokumentum ahhoz, hogy kihagyja az ellenőrzést | [Kiolvasó motor](02-parsing-engine.md) |
| **mentési kapu** | az ellenőrző pulton: ugyanazok a validátorok ítélik meg, amit az operátor beír | [Kiolvasó motor](02-parsing-engine.md) |
| **PII-kapu** | ügyfélszámla tartalma nem kerül LLM elé, a fejlesztő ügynökök elé sem | [Az adat útja](03-data-path.md) |
| **napindító kapu** | nincs kódmódosítás, commit vagy küldés, amíg a session nyitó rutinja le nem futott | [Munkamód](07-how-i-worked.md) |
| **kilépési kapu** (piacra lépés) | mikor hagyjuk el az egyik értékesítési csatornát a következőért | [Piac és árazás](06-market-and-pricing.md) |
