# ARCH-DOC: docs/architecture/06-clearadmin-billing-integration.md
"""S197 Fázis 4 — adókezelés-resolver: az EGYETLEN routing-seam (OSS-fogadó terv #1).

A checkout (api/routes/client_billing.py) NEM tartalmaz inline adójogi ágazást —
ide delegál (N-tier). A döntés két FÜGGETLEN tényből áll (terv-SoT:
.session/NIF_EUVAT_SEPARATION_PLAN_2026-07-23.md):

  nif_status == 'verified'   → IDENTITÁS-kapu (ki a cég — a mai szabály)
  vies_status == 'active'    → ADÓJOGI kapu (RC-jogosultság, vhr. 282/2011 18(1)(a))

Visszatérés: (treatment, reason)
  ('reverse_charge', None)            — mindkét kapu nyitva; RC 0% (Art. 196)
  ('blocked', 'nif_unverified')       — identitás hiányzik (mai hibaút)
  ('blocked', 'vies_not_active')      — NIF ok, de nincs VIES-aktiválás → könyvelői
                                        teendő (pending_registration türelmes állapot)

FENNTARTOTT jövőbeli treatment: 'oss_pt_iva' (B-sáv, POST-PILOT) — nem-VIES cég
PT IVA 23% OSS-en át; bekötése = itt egy új ág + a checkout egy új Stripe-ága,
a route nem változik. NE építs falat elé.
"""


def resolve_tax_treatment(client) -> tuple[str, str | None]:
    """(treatment, reason) — lásd modul-docstring. Pure function, DB-t nem ér."""
    if getattr(client, "nif_status", None) != "verified":
        return ("blocked", "nif_unverified")
    if getattr(client, "vies_status", None) != "active":
        # pending_registration / lapsed / NULL — RC-hez élő VIES-bizonyíték kell
        return ("blocked", "vies_not_active")
    return ("reverse_charge", None)
