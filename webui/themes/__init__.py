"""Theme loading helpers for the web UI."""

from __future__ import annotations

import logging
import os
import plistlib
from typing import Dict, List, Optional, Tuple

# (content same as earlier)

logger = logging.getLogger(__name__)

def _channel_to_int(value: Optional[float]) -> int:
    if value is None:
        return 0
    if value > 1.0:
        if value > 255.0:
            value = value / 257.0
        return int(max(0, min(255, round(value))))
    return int(max(0, min(255, round(value * 255.0))))


def _plist_color_to_hex(data: Optional[dict]) -> str:
    if not isinstance(data, dict):
        return "#000000"
    r = _channel_to_int(data.get("Red Component"))
    g = _channel_to_int(data.get("Green Component"))
    b = _channel_to_int(data.get("Blue Component"))
    return "#{:02x}{:02x}{:02x}".format(r, g, b)


def _hex_to_rgb(color: str) -> Tuple[int, int, int]:
    color = color.lstrip("#")
    if len(color) == 3:
        color = "".join(ch * 2 for ch in color)
    if len(color) != 6:
        return (0, 0, 0)
    return tuple(int(color[i : i + 2], 16) for i in range(0, 6, 2))


def _blend_hex(hex_a: str, hex_b: str, ratio: float) -> str:
    ratio = max(0.0, min(1.0, ratio))
    ra, ga, ba = _hex_to_rgb(hex_a)
    rb, gb, bb = _hex_to_rgb(hex_b)
    r = int(round(ra * (1 - ratio) + rb * ratio))
    g = int(round(ga * (1 - ratio) + gb * ratio))
    b = int(round(ba * (1 - ratio) + bb * ratio))
    return "#{:02x}{:02x}{:02x}".format(r, g, b)


DEFAULT_THEMES: List[Dict[str, object]] = [
    {
        "name": "Builtin Dark",
        "kind": "dark",
        "vars": {
            "bg": "#0e1116",
            "muted": "#1a1f29",
            "text": "#e6edf3",
            "sub": "#9da7b3",
            "accent": "#7aa2f7",
            "border": "#2b3240",
            "hl-kw": "#c792ea",
            "hl-proto": "#82aaff",
            "hl-act": "#c3e88d",
            "hl-addr": "#f78c6c",
            "hl-num": "#ffcb6b",
            "link": "#7aa2f7",
            "link-visited": "#9fb7ff",
            "link-hover": "#99b4ff",
            "link-active": "#4f79d6",
        },
    },
    {
        "name": "Builtin Light",
        "kind": "light",
        "vars": {
            "bg": "#ffffff",
            "muted": "#f6f8fa",
            "text": "#24292f",
            "sub": "#57606a",
            "accent": "#0969da",
            "border": "#d0d7de",
            "hl-kw": "#005cc5",
            "hl-proto": "#0d6efd",
            "hl-act": "#27a744",
            "hl-addr": "#d73a49",
            "hl-num": "#e36209",
            "link": "#0969da",
            "link-visited": "#0552a3",
            "link-hover": "#074c9a",
            "link-active": "#0b6ed8",
        },
    },
]


def load_iterm_theme(path: str) -> Optional[Dict[str, object]]:
    try:
        with open(path, "rb") as handle:
            data = plistlib.load(handle)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    bg = _plist_color_to_hex(data.get("Background Color"))
    fg = _plist_color_to_hex(data.get("Foreground Color"))
    accent = _plist_color_to_hex(
        data.get("Ansi 4 Color") or data.get("Cursor Color") or data.get("Ansi 6 Color")
    )
    muted = _blend_hex(bg, fg, 0.15)
    sub = _blend_hex(fg, bg, 0.35)
    border = _blend_hex(bg, fg, 0.25)
    luminance = sum(
        component * weight for component, weight in zip(_hex_to_rgb(bg), (0.2126, 0.7152, 0.0722))
    ) / 255.0
    kind = "light" if luminance > 0.5 else "dark"
    hl_kw = accent or fg
    hl_proto = _blend_hex(accent or fg, fg, 0.5)
    hl_act = _blend_hex("#6cc644", fg, 0.4)
    hl_addr = _blend_hex("#f66a0a", fg, 0.4)
    hl_num = _blend_hex("#ffcb6b", fg, 0.4)
    base_link = accent or fg
    hover_target = "#ffffff" if kind == "dark" else "#000000"
    link_hover = _blend_hex(base_link, hover_target, 0.2)
    link_active = _blend_hex(base_link, fg, 0.35)
    link_visited = _blend_hex(base_link, sub, 0.5)
    return {
        "name": os.path.splitext(os.path.basename(path))[0],
        "kind": kind,
        "vars": {
            "bg": bg,
            "muted": muted,
            "text": fg,
            "sub": sub,
            "accent": accent,
            "border": border,
            "hl-kw": hl_kw,
            "hl-proto": hl_proto,
            "hl-act": hl_act,
            "hl-addr": hl_addr,
            "hl-num": hl_num,
            "link": base_link,
            "link-visited": link_visited,
            "link-hover": link_hover,
            "link-active": link_active,
        },
    }


def load_themes(theme_dir: str) -> List[Dict[str, object]]:
    """Load themes from `theme_dir`, falling back to built-ins on failure."""

    themes: List[Dict[str, object]] = []
    if theme_dir:
        if os.path.isdir(theme_dir):
            try:
                for entry in sorted(os.listdir(theme_dir)):
                    if not entry.lower().endswith(".itermcolors"):
                        continue
                    path = os.path.join(theme_dir, entry)
                    theme = load_iterm_theme(path)
                    if theme:
                        themes.append(theme)
                    else:
                        logger.debug("Skipping unreadable theme file %s", path)
            except Exception as exc:
                logger.warning(
                    "Failed to enumerate theme directory %s: %s", theme_dir, exc
                )
        else:
            logger.info("Theme directory %s not found; using built-in themes.", theme_dir)
    else:
        logger.debug("No theme directory configured; using built-in themes.")

    for default in DEFAULT_THEMES:
        if not any(
            t["name"] == default["name"] and t["kind"] == default["kind"]
            for t in themes
        ):
            themes.insert(0, default)
    for default in DEFAULT_THEMES:
        if not any(t["kind"] == default["kind"] for t in themes):
            themes.append(default)
    return themes
