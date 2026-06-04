"""
validators/keywords.py — Category keyword allowlists.

Keys MUST match config.CATEGORIES strings exactly (same accents, same casing).
"""
from __future__ import annotations

CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "GPUs":             ["rtx", "gtx", "rx ", "arc", "radeon", "geforce", "gpu", "tarjeta de video"],
    "CPUs":             ["i3", "i5", "i7", "i9", "ryzen", "core ultra", "procesador", "cpu"],
    "RAM":              ["ddr4", "ddr5", "dimm", "sodimm", "memoria ram", "gb ddr"],
    "Placas madre":     ["z790", "z690", "b650", "b550", "x570", "motherboard", "placa madre"],
    "Almacenamiento":   ["ssd", "nvme", "hdd", "m.2", "sata", "tb", "disco"],
    "Fuentes de poder": ["psu", "650w", "750w", "850w", "1000w", "fuente de poder", "modular"],
    "Disipadores":      ["cooler", "disipador", "aio", "120mm", "240mm", "360mm", "noctua", "be quiet"],
    "Cases":            ["case", "gabinete", "mid tower", "full tower", "atx", "matx", "itx"],
    "Monitores":        ["monitor", "hz", "ips", "va", "oled", "1080p", "1440p", "4k"],
}
