"""JSON settings loader with env and CLI overrides."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, MutableMapping, Optional, Sequence

DEFAULT_SETTINGS_PATH = Path("settings.json")
ENV_PREFIX = "ACLINSPECTOR_"


@dataclass(frozen=True)
class ServerSettings:
    host: str = "127.0.0.1"
    port: int = 8083
    prewarm_all: bool = False


@dataclass(frozen=True)
class PathsSettings:
    configs: Dict[str, str] = field(
        default_factory=lambda: {"asa": "configs/cisco", "fortigate": "configs/fortigate"}
    )
    themes_dir: str = "themes"
    cache_dir: Optional[str] = None
    logs_dir: str = "logs"
    settings_file: str = "settings.json"


@dataclass(frozen=True)
class PredictiveSearchSettings:
    enabled: bool = True
    mode: str = "prefix"
    limit: int = 50


@dataclass(frozen=True)
class DiskCacheSettings:
    enabled: bool = False
    manifest: str = "manifest.json"


@dataclass(frozen=True)
class FeatureSettings:
    predictive_search: PredictiveSearchSettings = field(default_factory=PredictiveSearchSettings)
    history_tracking: bool = True
    asa_highlighting: bool = True
    disk_cache: DiskCacheSettings = field(default_factory=DiskCacheSettings)


@dataclass(frozen=True)
class BetaSettings:
    enabled_modules: Sequence[str] = field(default_factory=tuple)
    config: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class UISettings:
    theme_preview_speed: float = 12.0


@dataclass(frozen=True)
class Settings:
    server: ServerSettings = field(default_factory=ServerSettings)
    paths: PathsSettings = field(default_factory=PathsSettings)
    features: FeatureSettings = field(default_factory=FeatureSettings)
    beta: BetaSettings = field(default_factory=BetaSettings)
    ui: UISettings = field(default_factory=UISettings)


class SettingsError(Exception):
    """Raised when settings loading or validation fails."""


def load_settings(
    path: Optional[Path] = None,
    *,
    env: Optional[Mapping[str, str]] = None,
    cli_overrides: Optional[Mapping[str, Any]] = None,
) -> Settings:
    """Load settings from JSON file with env/CLI overrides."""

    env = dict(env or os.environ)
    cli_overrides = dict(cli_overrides or {})

    config: Dict[str, Any] = _default_dict()

    settings_path = Path(path or config["paths"]["settings_file"]).expanduser().resolve()
    if settings_path.is_file():
        loaded = _read_json(settings_path)
        _deep_merge(config, loaded)

    env_overrides = _env_overrides(env)
    if env_overrides:
        _deep_merge(config, env_overrides)

    if cli_overrides:
        _deep_merge(config, cli_overrides)

    try:
        return _build_settings(config, settings_path)
    except Exception as exc:  # pragma: no cover - defensive
        raise SettingsError(str(exc)) from exc


def _default_dict() -> Dict[str, Any]:
    return {
        "server": {
            "host": "127.0.0.1",
            "port": 8083,
            "prewarm_all": False,
        },
        "paths": {
            "configs": {
                "asa": "configs/cisco",
                "fortigate": "configs/fortigate",
            },
            "themes_dir": "themes",
            "cache_dir": None,
            "logs_dir": "logs",
            "settings_file": str(DEFAULT_SETTINGS_PATH),
        },
        "features": {
            "predictive_search": {
                "enabled": True,
                "mode": "prefix",
                "limit": 50,
            },
            "history_tracking": True,
            "asa_highlighting": True,
            "disk_cache": {
                "enabled": False,
                "manifest": "manifest.json",
            },
        },
        "beta": {
            "enabled_modules": ["packet-check"],
            "config": {},
        },
        "ui": {
            "theme_preview_speed": 12.0,
        },
    }


_LEGACY_ENV_MAP: Dict[str, Sequence[str]] = {
    "CONFIGS_CISCO": ("paths", "configs", "asa"),
    "CONFIGS_FORTIGATE": ("paths", "configs", "fortigate"),
    "THEME_DIR": ("paths", "themes_dir"),
    "CACHE_DIR": ("paths", "cache_dir"),
    "LOG_DIR": ("paths", "logs_dir"),
    "SEARCH_LIMIT": ("features", "predictive_search", "limit"),
    "SEARCH_MODE": ("features", "predictive_search", "mode"),
    "SEARCH_ENABLED": ("features", "predictive_search", "enabled"),
    "HISTORY_ENABLED": ("features", "history_tracking"),
    "PREWARM_ALL": ("server", "prewarm_all"),
    "BETA_MODULES": ("beta", "enabled_modules"),
    "DISK_CACHE_ENABLED": ("features", "disk_cache", "enabled"),
}


def _env_overrides(env: Mapping[str, str]) -> Dict[str, Any]:
    overrides: Dict[str, Any] = {}
    for key, value in env.items():
        if not key.startswith(ENV_PREFIX):
            continue
        suffix = key[len(ENV_PREFIX) :]
        if "__" in suffix:
            path_keys = [segment.lower() for segment in suffix.split("__")]
            _apply_override(overrides, path_keys, _coerce_value(value))
            continue
        if suffix in _LEGACY_ENV_MAP:
            path_keys = list(_LEGACY_ENV_MAP[suffix])
            if suffix == "BETA_MODULES":
                coerced: Any = [segment.strip() for segment in value.split(",") if segment.strip()]
            else:
                coerced = _coerce_value(value)
            _apply_override(overrides, path_keys, coerced)
    return overrides


def _apply_override(target: MutableMapping[str, Any], keys: Sequence[str], value: Any) -> None:
    cursor: MutableMapping[str, Any] = target
    for key in keys[:-1]:
        if key not in cursor or not isinstance(cursor[key], MutableMapping):
            cursor[key] = {}
        cursor = cursor[key]  # type: ignore[assignment]
    cursor[keys[-1]] = value


def _coerce_value(value: str) -> Any:
    text = value.strip()
    lowered = text.lower()
    if lowered in {"1", "true", "yes", "on"}:
        return True
    if lowered in {"0", "false", "no", "off"}:
        return False
    try:
        return int(text)
    except ValueError:
        try:
            return float(text)
        except ValueError:
            pass
    if "," in text:
        return [segment.strip() for segment in text.split(",") if segment.strip()]
    return text


def _read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _build_settings(config: Dict[str, Any], settings_path: Path) -> Settings:
    server = ServerSettings(**config["server"])
    paths = PathsSettings(**config["paths"])
    features = FeatureSettings(
        predictive_search=PredictiveSearchSettings(**config["features"]["predictive_search"]),
        history_tracking=bool(config["features"].get("history_tracking", True)),
        asa_highlighting=bool(config["features"].get("asa_highlighting", True)),
        disk_cache=DiskCacheSettings(**config["features"]["disk_cache"]),
    )
    beta = BetaSettings(
        enabled_modules=tuple(config["beta"].get("enabled_modules", [])),
        config=dict(config["beta"].get("config", {})),
    )
    ui = UISettings(**config["ui"])
    settings = Settings(server=server, paths=paths, features=features, beta=beta, ui=ui)
    object.__setattr__(settings.paths, "settings_file", str(settings_path))
    _normalize_paths(settings.paths, settings_path)
    _normalize_beta_modules(settings)
    return settings


def _resolve_path(value: Optional[str], base: Path) -> Optional[str]:
    if value is None:
        return None
    path = Path(value).expanduser()
    if path.is_absolute():
        return str(path)
    return str((base / path).resolve())


def _normalize_paths(paths: PathsSettings, settings_path: Path) -> None:
    base = settings_path.parent
    resolved_configs = {}
    for vendor, location in paths.configs.items():
        if not location:
            resolved_configs[vendor] = location
            continue
        resolved_configs[vendor] = _resolve_path(location, base)
    object.__setattr__(paths, "configs", resolved_configs)
    object.__setattr__(paths, "themes_dir", _resolve_path(paths.themes_dir, base) or paths.themes_dir)
    if paths.cache_dir:
        object.__setattr__(paths, "cache_dir", _resolve_path(paths.cache_dir, base))
    object.__setattr__(paths, "logs_dir", _resolve_path(paths.logs_dir, base) or paths.logs_dir)


def _normalize_beta_modules(settings: Settings) -> None:
    normalized = []
    seen = set()
    for module in settings.beta.enabled_modules:
        text = str(module or "").strip().lower().replace("_", "-")
        if not text:
            continue
        if text in seen:
            continue
        seen.add(text)
        normalized.append(text)
    object.__setattr__(settings.beta, "enabled_modules", tuple(normalized))


def _deep_merge(target: MutableMapping[str, Any], source: Mapping[str, Any]) -> None:
    for key, value in source.items():
        if (
            key in target
            and isinstance(target[key], MutableMapping)
            and isinstance(value, Mapping)
        ):
            _deep_merge(target[key], value)  # type: ignore[arg-type]
        else:
            target[key] = value  # type: ignore[assignment]
