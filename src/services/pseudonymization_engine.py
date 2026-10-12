"""Karakterazonos, HMAC-determinisztikus pszeudonimizáló mag (P0-3).

FONTOS: ez PSZEUDONIMIZÁCIÓ, nem anonimizáció (GDPR Rec. 26 — a kimenet
továbbra is személyes adat; doc45 §9.3). A modell DEFAULT-DENY: minden token
maszkolódik, kivéve az allowlist-találat és a tisztán strukturális tokenek.

Standalone: nincs DB, nincs route, nincs pipeline-import — pure Python.
Fogyasztók: scripts/privacy/pseudonymize_folder.py (mappa-CLI).

Karakter-szabályok (betűszám-azonos csere):
  - nagybetű  → nagybetű  (A-Z; ékezetes nagybetű is ASCII nagybetűre)
  - kisbetű   → kisbetű   (a-z; ékezetes kisbetű is ASCII kisbetűre)
  - számjegy  → számjegy  (0-9)
  - minden más (írásjel, whitespace, szimbólum) VÁLTOZATLAN
Determinizmus: HMAC-SHA256(secret, token) — ugyanaz a token ugyanazt a
maszkot kapja a futáson belül (fejléc-NIF == QR-NIF == lábléc-NIF reláció
megmarad). A secret futás-szintű, efemer (nem perzisztál).
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import string
import unicodedata
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - a vékony claude-dev gateway-ben PyYAML opcionális
    yaml = None  # type: ignore[assignment]


_WS_SPLIT_RE = re.compile(r"(\s+)")
_NUMERIC_LEAK_RE = re.compile(r"^\d{4,}$")
_PT_NIF_RE = re.compile(r"^\d{9}$")
# AT szoftver-tanúsítvány token ("Processado por programa certificado n.º 1234/AT")
# — a cert a SZOFTVER publikus azonosítója, nem személyes adat, és a séma-tanulás
# kulcsa (FileSchemaRegistry cert-index): never-mask kivétel (S202 scout-lelet).
_CERT_AT_RE = re.compile(r"^\d{1,4}/at$", re.IGNORECASE)


def _keystream(secret: bytes, token: str, length: int) -> bytes:
    """HMAC-SHA256 kulcsolt bájt-stream egy tokenhez.

    Első blokk: HMAC(secret, token). Ha ez nem elég hosszú, a folytatás
    HMAC(secret, token + str(counter)) növekvő counter-rel (1, 2, ...).
    """
    base = token.encode("utf-8")
    out = bytearray()
    counter = 0
    while len(out) < length:
        msg = base if counter == 0 else base + str(counter).encode("utf-8")
        out.extend(hmac.new(secret, msg, hashlib.sha256).digest())
        counter += 1
    return bytes(out[:length])


def _transform_char(c: str, b: int) -> str:
    """Egy karakter karakterosztály-őrző cseréje a keystream b bájtja alapján."""
    cat = unicodedata.category(c)
    if cat in ("Lu", "Lt"):
        return chr(ord("A") + (b % 26))
    if cat == "Ll":
        return chr(ord("a") + (b % 26))
    if c.isalpha():
        # Case nélküli betű (ritka a PT korpuszban) — konzervatív kisbetű-alap.
        return chr(ord("a") + (b % 26))
    if c.isdecimal():
        return chr(ord("0") + (b % 10))
    return c


class MaskContext:
    """Egy futás (köteg) maszk-kontextusa. A secret a teljes futásra közös."""

    def __init__(self, secret: bytes | None = None) -> None:
        """secret=None → secrets.token_bytes(32) (efemer, futás-szintű)."""
        self._secret = secret if secret is not None else secrets.token_bytes(32)
        self._cache: dict[str, str] = {}
        self._masked = 0
        self._allowed = 0
        self._structural = 0

    def mask_token(self, token: str) -> str:
        """Egyetlen token determinisztikus, karakterosztály-őrző maszkja.

        len(mask_token(t)) == len(t) MINDEN inputra; nem-alfanumerikus
        karakterek pozíció-helyesen változatlanok.
        """
        cached = self._cache.get(token)
        if cached is not None:
            return cached
        keystream = _keystream(self._secret, token, len(token))
        result = "".join(_transform_char(c, keystream[i]) for i, c in enumerate(token))
        self._cache[token] = result
        return result

    def mask_text(self, text: str, allowlist: frozenset[str]) -> str:
        """Teljes szöveg maszkolása default-deny elvvel.

        Whitespace-határokon tokenizál; egy token akkor marad nyersen, ha
        az írásjelektől megtisztított, kisbetűsített alakja az allowlistben
        van, VAGY tisztán strukturális (is_structural). Minden más token
        mask_token()-en megy át. A whitespace-szerkezet változatlan.
        """
        out_parts: list[str] = []
        for part in _WS_SPLIT_RE.split(text):
            if not part:
                continue
            if part.isspace():
                out_parts.append(part)
                continue
            if is_structural(part):
                self._structural += 1
                out_parts.append(part)
                continue
            stripped = part.strip(string.punctuation).lower()
            if stripped in allowlist or _CERT_AT_RE.match(stripped):
                self._allowed += 1
                out_parts.append(part)
                continue
            self._masked += 1
            out_parts.append(self.mask_token(part))
        return "".join(out_parts)

    @property
    def stats(self) -> dict:
        """Számlálók a futás-riporthoz: {"masked": int, "allowed": int,
        "structural": int}. ÉRTÉKEKET SOHA nem tartalmaz."""
        return {
            "masked": self._masked,
            "allowed": self._allowed,
            "structural": self._structural,
        }


def is_structural(token: str) -> bool:
    """True, ha a token tisztán írásjel/whitespace/szimbólum (nincs benne
    betű és számjegy) — ezek maszkolás nélkül átmennek."""
    return not any(c.isalpha() or c.isdecimal() for c in token)


def _is_numeric_leak(word: str) -> bool:
    """Védőszűrő: ≥4-jegyű tiszta számsor vagy PT NIF-formátum (9 jegy)."""
    return bool(_NUMERIC_LEAK_RE.match(word)) or bool(_PT_NIF_RE.match(word))


def _collect_strings(value: object, out: set[str]) -> None:
    """Rekurzívan összegyűjt minden string-levelet (list/dict/nested)."""
    if isinstance(value, str):
        out.add(value)
    elif isinstance(value, list):
        for item in value:
            _collect_strings(item, out)
    elif isinstance(value, dict):
        for item in value.values():
            _collect_strings(item, out)


def _walk_yaml_tree(node: object, out: set[str]) -> None:
    """A teljes YAML-fát bejárja, és a `keywords` / `column_keywords`
    kulcsú csomópontokból (bárhol a fában) kiszedi a string-értékeket.
    Semmilyen más kulcsot (schema_info, description, rejection_keywords...)
    NEM érint."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key in ("keywords", "column_keywords"):
                _collect_strings(value, out)
            _walk_yaml_tree(value, out)
    elif isinstance(node, list):
        for item in node:
            _walk_yaml_tree(item, out)


def load_allowlist(repo_root: Path) -> frozenset[str]:
    """Never-mask allowlist építése. KIZÁRÓLAG ezekből a forrásokból:
      - schemas/masters/*.yaml + schemas/deltas/**/*.yaml:
        `detection.keywords` és `column_keywords` kulcsok (SEMMI más kulcs —
        a schema_info/description valódi azonosítókat tartalmaz, K3-lelet!)
      - BUILTIN_PT_LABELS (induló címke-készlet, doc48 label_aliases-ig)
    Minden elem kisbetűsítve. VÉDŐSZŰRŐ: ami NIF-mintára (\\d{9}) vagy
    bármilyen ≥4 hosszú tiszta számsorra illeszkedik, KIESIK az allowlistből.
    """
    raw: set[str] = set()

    if yaml is not None:
        masters_dir = repo_root / "schemas" / "masters"
        deltas_dir = repo_root / "schemas" / "deltas"
        paths = list(masters_dir.glob("*.yaml")) + list(deltas_dir.glob("**/*.yaml"))
        for path in paths:
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    data = yaml.safe_load(fh)
            except Exception:
                # Hibatűrő olvasás: egy rossz/hibás YAML nem dönti el a futást.
                continue
            if isinstance(data, (dict, list)):
                _walk_yaml_tree(data, raw)
    # ha nincs PyYAML (vékony claude-dev gateway) → csak a BUILTIN listával
    # megyünk tovább, nem hasal el.

    raw |= set(BUILTIN_PT_LABELS)

    # Többszavas keyword-öket szavakra is bontjuk (szó-szintű tokenizálás).
    words: set[str] = set()
    for kw in raw:
        for w in re.split(r"\s+", kw.strip()):
            if w:
                words.add(w)
    raw |= words

    lowered = {w.lower() for w in raw if w}
    return frozenset(w for w in lowered if not _is_numeric_leak(w))


# Induló strukturális címke-készlet (doc48 label_aliases kódolásáig).
# CSAK generikus layout-szavak — ide SOHA nem kerülhet érték/név/azonosító.
# TODO(doc48): ezt a listát a label_aliases kódolásakor kanonikus forrásra
# kell cserélni (jelenleg kézzel karbantartott, konzervatív PT-címke-halmaz).
BUILTIN_PT_LABELS: frozenset[str] = frozenset(
    {
        "fatura", "factura", "recibo", "fatura-recibo", "nota", "credito", "crédito",
        "debito", "débito", "nif", "iva", "contribuinte", "atcud", "total", "subtotal",
        "data", "vencimento", "emissao", "emissão", "quantidade", "descricao", "descrição",
        "designacao", "designação", "preco", "preço", "valor", "taxa", "unidade", "un",
        "qtd", "original", "duplicado", "via", "pagina", "página", "eur", "euro", "morada",
        "telefone", "email", "iban", "isento", "continuacao", "artigo", "referencia",
        "referência", "documento", "cliente", "fornecedor", "lda", "unipessoal", "s.a.", "sa",
    }
)
