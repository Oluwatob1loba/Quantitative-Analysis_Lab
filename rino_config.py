"""RINO config - typed live snapshots of the CORE input panel + research additions.
Provenance: architect screenshots 16 Oct 2026; architect rulings 17 Oct 2026
(D-PY-05 width, D-PY-06 ADD-01 rev2, D-PY-07 Sydney provisional, D-PY-08 UTC+1,
D-PY-09 Sunday fold, D-PY-10 universal majors). Source-default authority: P5 register."""
from dataclasses import dataclass, field
from typing import List


@dataclass
class AnchorCfg:
    tf: str
    candles: int
    enabled: bool
    fvg: bool


@dataclass
class SessionCfg:
    """Key-time window in FIXED UTC+1 minutes-from-midnight (DR-25 freeze value)."""
    name: str
    start_min: int
    end_min: int
    provisional: bool = False


KEY_TIMES: List[SessionCfg] = [
    SessionCfg("New York", 14 * 60, 16 * 60),
    SessionCfg("London",    8 * 60, 10 * 60),
    SessionCfg("Tokyo",     0 * 60,  3 * 60 + 30),
    SessionCfg("Sydney",   21 * 60, 23 * 60 + 30, provisional=True),
]


@dataclass
class RinoConfig:
    name: str
    # TF1 macro layer
    tf1: str
    tf1_lookback: int
    tf1_sub_lookback: int
    tf1_show_open: bool = False      # D-PY-05: checkbox only
    tf1_line_width: int = 2          # D-PY-05: the numeric field is WIDTH
    tf1_mid_lookback: int = 1
    tf1_open_lookback: int = 0
    # TF2 structure layer
    tf2: str = "1D"
    tf2_anchor_to_tf1: bool = True
    tf2_manual_lookback: int = 10
    tf2_width: int = 1
    tf2_show_minor: bool = True
    tf2_highlight_critical: bool = True
    tf2_critical_proximity_pct: float = 0.1
    tf2_critical_on_minor: bool = True
    # D-PY-18: True = frozen-source semantics (High vs parent High, Low vs parent Low,
    # denominator abs(parentPrice); C:L457..L497, P4.2). False = legacy min-distance
    # variant. Pending architect ratification; handover recommends True (§18.1).
    critical_side_matched: bool = True
    tf2_faded_opacity_pct: int = 30
    # Anchors
    anchors: List[AnchorCfg] = field(default_factory=list)
    anchor_line_width: int = 2
    tf2_sweep_layer: bool = False
    tf2_draws_in_tf1_target_math: bool = False
    # V3 setups / key levels (shared blocks per screenshots)
    retained_ts_events: int = 12
    stop_buffer_ticks: int = 1          # v3StopTicksInput (P5)
    q1: bool = True
    q2: bool = True
    q3: bool = True
    q4: bool = False
    tf1_fvg: bool = True
    tf2_fvg: bool = False
    tf1_vi: bool = False
    tf2_vi: bool = False
    min_vi_width_pct: float = 0.0
    zone_drawing_life: int = 2
    retained_zones: int = 12
    zone_age: int = 12
    fvg_midline: bool = True
    v3_dol_proximity_pct: float = 0.1
    # Ranking weights (source defaults, corroborated by screenshot)
    w_opposes_owner: float = -1
    w_dol_confluence: float = 1
    w_htf_alignment: float = 1
    w_fvg_vi: float = 1
    w_critical_break: float = 2
    w_major_break: float = 1
    w_minor_break: float = -1
    w_anchor_priority: float = 1
    w_undisturbed_tf1: float = 1
    w_anchor_pdol_scan: int = 4
    grade_a_threshold: float = 5
    grade_b_threshold: float = 2
    # ADD-01 rev 2: key-time liquidity raid (arena = any TF1; raid timed on LTF)
    key_time_sweep_weight: float = 1.0
    gate_on_key_time_sweep: bool = False
    key_time_check_tf: str = "15min"
    key_times: List[SessionCfg] = field(default_factory=lambda: KEY_TIMES)
    utc_offset_fixed: int = 1
    # D-PY-33 (architect ruling 2026-10-28): admission mode.
    # 'full' = frozen Model-3 stack (TSM direction gate + FVG POI gate ACTIVE) - default,
    #          byte-identical to the certified port.
    # 'm2'   = raw price-delivery population: BOTH gates bypassed at record time
    #          (episodes still require a tradeable PDOL target). Geometry is stamped on
    #          every admitted setup; breakClass/confluence/class remain as EVIDENCE,
    #          non-gating. M3 records and M2 population never share a CSV.
    admission: str = 'full'



PRESET_A = RinoConfig(
    name="PRESET_A_unattributed",
    tf1="1D", tf1_lookback=15, tf1_sub_lookback=13, tf2="4h",
    anchors=[AnchorCfg("1W", 5, True, True), AnchorCfg("1M", 5, True, True),
             AnchorCfg("3M", 3, True, False)],
)
PRESET_AUDUSD = RinoConfig(
    name="AUDUSD",
    tf1="1W", tf1_lookback=8, tf1_sub_lookback=8, tf2="1D",
    anchors=[AnchorCfg("1W", 5, False, False), AnchorCfg("1M", 5, True, True),
             AnchorCfg("3M", 3, True, False)],
)
PRESETS = {p.name: p for p in (PRESET_A, PRESET_AUDUSD)}


def config_for(symbol: str) -> RinoConfig:
    """D-PY-10: universal recipe for the majors; per-symbol TF ladders arrive with
    the architect's table. Until then TF1/TF2 are experiment dials, not dogma."""
    return PRESETS.get(symbol, PRESET_A)