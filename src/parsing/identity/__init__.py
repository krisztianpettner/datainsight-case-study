"""
parsing.identity — S182 adat-azonossági réteg (Fázis 1).

A vak conf% (QR-jelenlét-proxy) lecserélése verifikáció-először adat-azonossági
becslésre. Három egység:

  normalize_compare — típus-tudatos kanonizál + 3/4-utas Verdict (MATCH/MISMATCH/
                      POSSIBLE/INSUFFICIENT). A fundamentum, dep-mentes.
  field_catalog     — a kanonikus mező → {qr_slot, visual_slot, field_type,
                      verifiable_class, critical} térkép (a slot-alias, a S182
                      key-probe-bal igazolva: .session/S182_keyprobe_result.md).
  qr_reconcile      — a QR-olvasat vs a vizuális olvasat összevetése egy kanonikus
                      mezőn (a QR mint VALIDÁTOR, nem 1.0-pontforrás).
  field_identity    — per-mező identity_estimate (verifikáció-először) + doc-szintű
                      aggregate (min a kritikus (a)/(b) mezőkön).

Design SoT: .session/S182_data_identity_metric_research_and_design.md +
            .session/S182_field_catalog_and_verifiability_map.md +
            .session/S182_phase1_plan_parsing_identity.md
"""
