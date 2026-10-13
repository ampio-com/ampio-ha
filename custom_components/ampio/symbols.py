"""Ampio module symbols, matching Designer typPcbToSymbolName."""

from __future__ import annotations

from typing import Any

# typ -> pcb version -> symbol. pcb 0 is the default for that type.
SYMBOL_NAMES: dict[int, dict[int, str]] = {
    -1: {0: "CAN"},
    1: {0: "M-IN-4p"},
    2: {0: "M-PR-1p"},
    3: {0: "M-ROL-4s"},
    4: {0: "M-REL-8s"},
    5: {0: "M-DIM-8s"},
    6: {0: "M-AV-AMP-s"},
    7: {0: "INT-LCD"},
    8: {0: "M-DOT-4", 5: "M-DOT-DLUGI4"},
    9: {0: "M-DOT-18"},
    10: {0: "M-SERV-s", 8: "M-SERV-MINI-s", 11: "M-SERV-MINI-s"},
    11: {0: "M-DOT-9"},
    12: {0: "M-RGBW"},
    13: {0: "MTR-4"},
    14: {0: "M-INOC-8s", 5: "M-OC-C8s", 8: "M-OC-C8s"},
    15: {0: "M-IN-8s"},
    16: {0: "MRTC-1"},
    17: {0: "M-LED-s"},
    18: {0: "M-DIM-1p", 3: "M-DIM-1s"},
    19: {0: "M-RT-1s"},
    20: {0: "M-RT-4s"},
    21: {0: "M-RT-8s"},
    22: {0: "M-RT-16s"},
    23: {0: "M-RT-32s"},
    24: {0: "M-REL-2s", 9: "M-REL-2p", 11: "M-REL-2p"},
    25: {
        0: "M-CON-s",
        2: "M-CON-232-s",
        4: "M-CON-232-s",
        6: "M-CON-232-s",
        3: "M-CON-485-s",
        5: "M-CON-485-s",
        7: "M-CON-485-s",
    },
    26: {
        0: "M-INOC-4p",
        11: "M-OC-4s",
        15: "M-OC-4s",
        16: "M-OC-4s",
        18: "M-OC-4s",
    },
    27: {0: "MDOT-15LCD"},
    28: {0: "M-IN-AC4s"},
    29: {0: "M-IN-AD8s"},
    30: {0: "M-CON-IR"},
    31: {0: "MROL-1"},
    32: {0: "M-DOT-6"},
    33: {0: "M-DOT-2"},
    34: {0: "M-METEO"},
    35: {0: "M-CON-CAN-s"},
    36: {0: "M-DOT-GEST"},
    37: {0: "M-CON-ZWAVE-s"},
    38: {0: "M-RDN-5s"},
    39: {0: "M-OUT-4s", 2: "M-OUT-4p"},
    40: {0: "M-IN-11p"},
    41: {0: "M-OC-32s"},
    42: {0: "M-IN-16s"},
    43: {0: "M-CON-DALI-s"},
    44: {0: "M-SENS"},
    45: {0: "MSMOG"},
    46: {0: "M1WGW"},
    47: {0: "M-CON-KNX-s"},
    48: {0: "MEXL"},
    49: {0: "M-IN-RKE4-p"},
    50: {0: "USBGW"},
    51: {0: "M-DOT-M6"},
    52: {0: "M-DOT-M14"},
    53: {0: "GPS-ALARM"},
    54: {0: "M-IN-PTK3p", 2: "M-IN-TCD3p"},
    55: {0: "MIN16OC8"},
    56: {0: "M-AV-MP3s"},
    57: {0: "MRFID"},
    58: {0: "MRFKEY"},
    59: {0: "MDISPLAY"},
    60: {0: "M-DOT-M15"},
    61: {0: "M-ROOM-s"},
    62: {0: "MREL10", 1: "M-REL-10s", 2: "M-REL-C10s"},
    63: {0: "M-CON-ENOCN-p"},
    64: {0: "M-DOT-M6"},
    65: {0: "MBLE"},
    66: {0: "M-ALARM-8s"},
    67: {0: "M-CON-WL-p"},
    68: {0: "M-DOT-M18"},
    69: {0: "M-DIM-2s"},
    70: {0: "M-IN-2p"},
    72: {0: "M-REL-4", 1: "M-REL-C4s"},
    73: {0: "M-DOT-R14"},
    74: {0: "M-CON-KEY-p"},
    75: {0: "M-CON-WZ-p"},
    76: {0: "M-CON-HVAC-p"},
    77: {0: "M-IN-IMP-4s"},
    78: {0: "M-DOT-T6"},
    79: {0: "M-DOT-R PRO"},
    80: {0: "M-DOT-R2 PRO"},
    81: {0: "M-CON-WS-p"},
    82: {0: "M-CON-HVAC_SNIFFER-p"},
    83: {0: "M-CON-UART-p"},
    256: {0: "VIRTUAL"},
}


def symbol_name(typ: Any, pcb: Any = 0) -> str:
    """Resolve typ_urzadzenia and wersja_pcb the same way Designer does."""
    try:
        typ_number = int(typ)
    except (TypeError, ValueError):
        return ""
    try:
        pcb_number = 0 if pcb in (None, "") else int(pcb)
    except (TypeError, ValueError):
        pcb_number = 0
    variants = SYMBOL_NAMES.get(typ_number)
    if variants is None:
        return f"unknown, typ={typ_number}"
    return variants.get(pcb_number) or variants.get(0) or f"unknown typ={typ_number}"
