"""rino_pairings.py - timeframe ladders the system can reach for (D-PY-32).

UNIVERSAL TIME-STRUCTURE PAIRINGS. Architect ruling (2026-10-28): these
ladders cut across FX, metals, and indices - an asset class does not own a
ladder, it reaches for one. New asset classes map onto existing ladders
until a battery justifies their own.

One named ladder: which TF1 the engine thinks in, which TF2 computes
structure on (NEVER the same as TF1 - swing points, alternation, 0.1%
Critical matching, and bias do NOT apply to TF1's own data), which anchors
supply draws, and the suggested entry timeframe(s) below TF1.

Sources (authority order per D-PY-29):
- "current lab preset" = the freeze-log bake config (verified running)
- CRT & TS Guide p.16 ladder (HTF key level -> CRT TF)
- RANGE_POI_MIT Notes p.14 pairing page (framework - hypothesis until gated)

EXPANSION RULE: a new ladder enters only after passing the standard battery
on at least one symbol. A ladder is config, never behavior - the predicates
stay frozen.
"""

# ladder fields:
#   tf1     - engine timeframe (episodes, DOLs, sweeps)
#   tf2     - structure timeframe (swings, alternation, bias, CHoCH, Critical)
#             Rule: tf2 is ALWAYS the chart below tf1, never tf1 itself.
#   anchors - draw/target slots, highest-authority first
#   entry   - suggested execution timeframe(s) below tf1
#   source  - where the pairing came from
LADDERS = {
    "FX_W1": dict(tf1="1W", tf2="1D", anchors=["1M", "3M"],
                  entry=["H4", "H2"], source="architect ruling 2026-10-28; universal across metals/indices too"),
    "FX_D1": dict(tf1="1D", tf2="4H", anchors=["1W", "1M", "3M"],
                  entry=["H1", "M30"], source="current lab preset (freeze-log bake)"),
    "FX_H4": dict(tf1="4H", tf2="H1", anchors=["1D", "1W", "1M"],
                  entry=["M30", "M15"], source="alias of FX_D1 - universal ladder (CRT guide p.16, D1,H4 -> H1)"),
    "FX_H1": dict(tf1="H1", tf2="M15", anchors=["H4", "1D", "1W"],
                  entry=["M5"], source="CRT guide p.16 (H4,H1 -> 15M)"),
    "FX_M15": dict(tf1="M15", tf2="M5", anchors=["H1", "H4", "1D"],
                   entry=["M1"], source="RANGE notes p.14 (M30/M15 -> M1)"),
    "METALS_D1": dict(tf1="1D", tf2="4H", anchors=["1W", "1M", "3M"],
                      entry=["H1", "M30"], source="alias of FX_D1 - universal ladder (architect ruling 2026-10-28)"),
    "INDEX_D1": dict(tf1="1D", tf2="4H", anchors=["1W", "1M", "3M"],
                     entry=["H1", "M30"], source="CRT guide p.16 (D1,H4 -> H1)"),
    "EQUITY_D1": dict(tf1="1D", tf2="4H", anchors=["1W", "1M", "3M"],
                      entry=["H1"], source="provisional - pending battery (hypothesis, not ratified)"),
}

DEFAULT = "FX_D1"

# higher-timeframe pairing view (RANGE notes p.14): framework TF -> (structure, execution)
FRAMEWORK_VIEW = {
    "3M": ("M/W", "W/D"), "M": ("W", "D"), "W": ("D", "H4"),
    "D": ("H4", "H1/M30"), "H4": ("H1", "M30/M15"), "H1": ("M30/M15", "M5"),
    "M30/M15": (None, "M1"),
}


def get(name=None):
    """Return a ladder by name (defaults to DEFAULT). Raises on unknown names -
    silence is a defect (SR-1)."""
    name = name or DEFAULT
    if name not in LADDERS:
        raise KeyError(f"unknown ladder '{name}'. known: {sorted(LADDERS)}")
    return dict(LADDERS[name], name=name)


if __name__ == "__main__":
    for k, v in LADDERS.items():
        star = "*" if k == DEFAULT else " "
        print(f"{star} {k:<10} tf1={v['tf1']:<4} tf2={v['tf2']:<4} "
              f"anchors={','.join(v['anchors']):<10} entry={','.join(v['entry']):<8} [{v['source']}]")
