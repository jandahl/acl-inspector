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


def _rgba_string(color: str, alpha: float) -> str:
    """Convert a hex color to an rgba() string with the given alpha."""

    r, g, b = _hex_to_rgb(color)
    alpha = max(0.0, min(1.0, float(alpha)))
    alpha_text = ("{:.3f}".format(alpha)).rstrip("0").rstrip(".")
    return f"rgba({r}, {g}, {b}, {alpha_text})"


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


def build_singularity_palette(theme: Dict[str, object]) -> Dict[str, str]:
    """Derive Singularity UI color tokens from a base theme."""

    vars_map = theme.get("vars", {}) if isinstance(theme, dict) else {}
    bg = vars_map.get("bg", "#0e1116")
    muted = vars_map.get("muted", _blend_hex(bg, "#ffffff", 0.08))
    text = vars_map.get("text", "#e6edf3")
    sub = vars_map.get("sub", _blend_hex(text, bg, 0.35))
    accent = vars_map.get("accent") or vars_map.get("link") or text
    border = vars_map.get("border", _blend_hex(bg, text, 0.22))
    kind = (theme.get("kind") if isinstance(theme, dict) else "dark") or "dark"
    is_light = str(kind).lower() == "light"

    accent_soft = _blend_hex(accent, text if is_light else "#ffffff", 0.35 if is_light else 0.2)
    accent_contrast = _blend_hex(accent, "#ffffff" if not is_light else "#000000", 0.28)
    bg_surface = _blend_hex(bg, accent, 0.08 if not is_light else 0.12)
    bg_muted = _blend_hex(bg_surface, bg, 0.4)
    chip_base = _blend_hex(accent, bg, 0.18 if not is_light else 0.22)
    hover_base = _blend_hex(bg_surface, accent, 0.25 if not is_light else 0.18)
    glow_primary = _blend_hex(accent, accent_contrast, 0.3)
    glow_secondary = _blend_hex(accent, text, 0.35 if is_light else 0.2)
    glow_tertiary = _blend_hex(accent_contrast, bg, 0.35 if is_light else 0.45)
    halo = _blend_hex(accent, text if is_light else "#ffffff", 0.25)
    shadow_base = _blend_hex(bg, "#000000" if not is_light else "#4a5568", 0.45)
    danger = _blend_hex("#ff6b6b", text, 0.35 if is_light else 0.45)
    focus_ring = _blend_hex(accent, text if is_light else "#ffffff", 0.32)

    return {
        "bg-base": bg,
        "bg-surface": bg_surface,
        "bg-muted": bg_muted,
        "bg-overlay": _rgba_string(bg_surface, 0.8 if not is_light else 0.75),
        "bg-glow-primary": glow_primary,
        "bg-glow-secondary": glow_secondary,
        "bg-glow-tertiary": glow_tertiary,
        "backdrop-primary": _rgba_string(_blend_hex(accent, bg, 0.35), 0.45 if not is_light else 0.35),
        "backdrop-secondary": _rgba_string(_blend_hex(accent, text, 0.18), 0.16),
        "halo": _rgba_string(halo, 0.22 if not is_light else 0.28),
        "text": text,
        "text-soft": _blend_hex(text, "#ffffff" if not is_light else bg, 0.2),
        "text-muted": sub,
        "border": _rgba_string(border, 0.24 if not is_light else 0.35),
        "border-strong": _rgba_string(_blend_hex(border, accent, 0.25), 0.45 if not is_light else 0.38),
        "accent": accent,
        "accent-soft": accent_soft,
        "accent-contrast": accent_contrast,
        "pill-bg": _rgba_string(_blend_hex(bg_surface, accent, 0.28), 0.78 if not is_light else 0.72),
        "pill-border": _rgba_string(_blend_hex(border, accent, 0.35), 0.32 if not is_light else 0.4),
        "suggestion-bg": _rgba_string(_blend_hex(bg_surface, accent, 0.22), 0.88 if not is_light else 0.82),
        "suggestion-hover": _rgba_string(hover_base, 0.95 if not is_light else 0.88),
        "chip-bg": _rgba_string(chip_base, 0.32 if not is_light else 0.28),
        "chip-text": _blend_hex(accent_soft, text, 0.45 if is_light else 0.6),
        "highlight": _rgba_string(_blend_hex(accent, text, 0.3), 0.38 if not is_light else 0.32),
        "shadow-color": _rgba_string(shadow_base, 0.6 if not is_light else 0.45),
        "danger": danger,
        "focus-ring": _rgba_string(focus_ring, 0.75 if not is_light else 0.55),
    }
