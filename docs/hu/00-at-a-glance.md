[English](../en/00-at-a-glance.md) · **Magyar** · [↑ README](../../README.hu.md)

# Áttekintés

## A rendszer egy képen

```mermaid
flowchart TB
    P([Pedro<br/>vállalkozó]) -->|PDF feltöltés| CF[Cloudflare<br/>WAF + bot-védelem]
    CF --> EDGE

    subgraph VPS["Nyilvános VPS — csak továbbít, soha nem dolgoz fel"]
        EDGE[edge app<br/>feltöltés · webhookok · push]
        PORTAL[portál app<br/>vállalkozói + könyvelői felület]
        PDB[(portál DB<br/>maszkolt vetület)]
        PORTAL --- PDB
    end

    EDGE -->|Tailscale| NAS[(NAS<br/>titkosított tároló)]
    NAS -->|LAN| PIPE

    subgraph PC["Helyi PC — az egyetlen hely, ahol nyers adat feldolgozódik"]
        PIPE[bemeneti ellenőrzés] --> QR[QR / vonalkód<br/>adóhatósági orákulum]
        QR --> T2[Tier 2: sémák + heurisztikák<br/>+ tételsor-létra]
        T2 -.csak ha egyik tételsor-réteg sem ad sort.-> T3[Tier 3: helyi LLM]
        T2 --> GATE{mezőnkénti<br/>azonossági kapu}
        T3 --> GATE
        GATE -->|igazolt| AUTO[automatikus jóváhagyás]
        GATE -->|nem igazolt| DESK[emberi ellenőrző pult]
        SOT[(feldolgozási DB<br/>az igazság forrása)]
    end

    AUTO --> EXP[export + státusz]
    DESK --> EXP
    EXP -->|maszkolt státusz| PDB
    PORTAL --> M([Maria<br/>könyvelő])
```

## Tizennégy döntés, amely meghatározza

Soronként egy mondat; a teljes rekord — kontextus, elvetett alternatívák, következmények — a
[döntés-rekordokban](a-decision-records.md) van.

| ADR | döntés | miért | ára |
|---|---|---|---|
| [01](a-decision-records.md#adr-01--nincs-felhős-feldolgozás) | **Nincs felhő.** A nyers számlát csak egy helyi PC dolgozza fel. | Az adatszuverenitás az ígéret a kisvállalkozóknak és a könyvelőknek. | Három gép, helyi OCR és LLM; a Cloudflare így is olvassa a feltöltést átmenetben. |
| [02](a-decision-records.md#adr-02--az-adóhatósági-qr-kód-az-orákulum) | **Az adóhatósági QR-kód az orákulum** a fejléc-értékekre. | Egy aláírt, az államnak jelentett forrás többet ér a modell önbizalmánál. | A QR nélküli számlákra (az arany-halmaz 21%-a) nincs orákulum. |
| [03](a-decision-records.md#adr-03--rétegzett-kiolvasás-a-helyi-modell-az-utolsó) | **Három szint:** QR → sémák, heurisztikák és tételsor-létra → helyi LLM utoljára. | Előbb az olcsó és determinisztikus. | Három kódút, amit egyben kell tartani. |
| [04](a-decision-records.md#adr-04--a-séma-adat) | **A séma adat:** országos master plusz számlázóprogramonként egy delta. | Egy új szállítói elrendezés egy YAML-fájl, nem kód. | A lefedettség programonként nő. |
| [05](a-decision-records.md#adr-05--precizitás-először-soha-nem-találgatunk) | **Soha nem találgatunk.** A hiányzó érték jobb a rossznál. | A hiányt az ellenőrzés elkapja; a magabiztos hiba eljut a könyvelőig. | Kisebb automatizáltság — szándékosan. |
| [06](a-decision-records.md#adr-06--mezőnkénti-azonossági-kapu-előbb-szigorúan) | **Mezőnkénti azonossági kapu**, előbb szigorúan, lazítás csak bizonyítékra. | A bizalomban van az érték. | A pilot-konfigurációban minden számla ellenőrzésre ment. |
| [07](a-decision-records.md#adr-07--két-alkalmazás-a-nyilvános-szerveren) | **Két alkalmazás a nyilvános szerveren:** vékony edge és a portál. | Egy feltört edge ne érje el az ügyféladat-logikát. | Két telepítendő egység. |
| [08](a-decision-records.md#adr-08--három-adatbázis-mint-három-csomópont) | **Három adatbázis három csomóponton;** az igazság a PC-n él. | A nyilvános szerver elveszhet anélkül, hogy az igazság elveszne — vagy kiszivárogna. | Kifejezetten megtervezendő szinkron-híd. |
| [09](a-decision-records.md#adr-09--rétegzett-kapcsolatok-a-feldolgozó-telephelyről-semmi-nem-látszik) | **Rétegzett kapcsolatok,** a feldolgozó telephelyről semmi nem látszik. | Minden ugrásnak egy feladata van. | Bármelyik réteg kiesése megállítja a folyamot (tartalék: SSH-húzás). |
| [10](a-decision-records.md#adr-10--a-vállalkozó-fizet-a-könyvelő-nem--és-jutalékot-sem-kap) | **A vállalkozó fizet; a könyvelő ingyen használja.** | Ő a csatorna: egy könyvelő az egész ügyfélkörét hozza. | Két felhasználói csoport, két felület. |
| [11](a-decision-records.md#adr-11--sávos-használat-alapú-árazás) | **Havi €39 + sávos használat** csomagok helyett. | A csomagok kredit-felhalmozási csapdát szültek. | Kevésbé kiszámítható bevétel. |
| [12](a-decision-records.md#adr-12--a-pii-kapu-az-építőre-is-vonatkozik) | **A PII-kapu a rendszert építő MI-re is vonatkozik.** | A no-cloud ígéretnek az építőre is érvényesnek kell lennie. | Hibakeresés csak maszkolt adaton. |
| [13](a-decision-records.md#adr-13--a-pénz-útja-felelősség-szerint-szétválasztva) | **A pénz útja felelősség szerint szétválasztva:** a Stripe beszed, a saját napló dönt, egy helyi program számláz. | Egy emberi jóváhagyás megváltoztatja a számlát; ennek ott kell auditálhatónak lennie, ahol születik. | Négy rendszer egyeztetése; a CSV-ig épült meg. |
| [14](a-decision-records.md#adr-14--a-pipeline-híd-mappa-szerződés-nem-api) | **A pipeline-híd mappa-szerződés, nem API.** | A feldolgozó gépnek nem kell nyitott port. | Lekérdezési késleltetés és jelölőfájlok. |

## Négy történet, amire érdemes rákérdezni

- **A bitre azonos lépcső** — hogyan lett kisebb egy 1 482 soros feladat egyetlen kimenet megváltoztatása nélkül. → [Platform](09-platform.md#megmérve-aztán-lépcsőnként-javítva)
- **A 17 napos néma mentési hiba** — 412 hibajelzés, amit senki nem kapott meg. → [Infrastruktúra](08-infrastructure.md#mentés-és-katasztrófa-helyreállítás)
- **A hamis nulla** — egy port-szkennelés, amely rossz okból jelzett „tisztát". → [Biztonság](07-security-and-isolation.md#a-határ--kimondva-aztán-megmérve)
- **A szám, amely mást mért** — a tételsor-arányok a labor-kiolvasón születtek, nem a produkción. → [Mérőszámok](b-metrics.md#a-mérési-tanulságok)
