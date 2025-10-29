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

    settings_path = Path(path or config["paths"]["settings_file"]).expanduser()
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
        return text


def _deep_merge(base: MutableMapping[str, Any], override: Mapping[str, Any]) -> None:
    for key, value in override.items():
        if isinstance(value, Mapping) and isinstance(base.get(key), MutableMapping):
            _deep_merge(base[key], value)  # type: ignore[arg-type]
        else:
            base[key] = value


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
            if not isinstance(data, dict):
                raise SettingsError(f"Settings file {path} must contain a JSON object")
            return data
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as exc:
        raise SettingsError(f"Failed to parse {path}: {exc}") from exc


def _build_settings(config: Mapping[str, Any], settings_path: Path) -> Settings:
    # Resolve paths relative to the settings file directory.
    base_dir = settings_path.parent

    server_conf = config["server"]
    server = ServerSettings(
        host=str(server_conf.get("host", "127.0.0.1")),
        port=int(server_conf.get("port", 8083)),
        prewarm_all=bool(server_conf.get("prewarm_all", False)),
    )

    paths_conf = config["paths"]
    configs_conf = paths_conf.get("configs", {})
    paths = PathsSettings(
        configs={
            "asa": str(configs_conf.get("asa", "configs/cisco")),
            "fortigate": str(configs_conf.get("fortigate", "configs/fortigate")),
        },
        themes_dir=str(paths_conf.get("themes_dir", "themes")),
        cache_dir=str(paths_conf.get("cache_dir")) if paths_conf.get("cache_dir") else None,
        settings_file=str(settings_path),
    )

    features_conf = config["features"]
    predictive_conf = features_conf.get("predictive_search", {})
    disk_cache_conf = features_conf.get("disk_cache", {})
    features = FeatureSettings(
        predictive_search=PredictiveSearchSettings(
            enabled=bool(predictive_conf.get("enabled", True)),
            mode=str(predictive_conf.get("mode", "prefix")),
            limit=int(predictive_conf.get("limit", 50)),
        ),
        history_tracking=bool(features_conf.get("history_tracking", True)),
        asa_highlighting=bool(features_conf.get("asa_highlighting", True)),
        disk_cache=DiskCacheSettings(
            enabled=bool(disk_cache_conf.get("enabled", False)),
            manifest=str(disk_cache_conf.get("manifest", "manifest.json")),
        ),
    )

    beta_conf = config["beta"]
    enabled_modules = beta_conf.get("enabled_modules", [])
    if isinstance(enabled_modules, str):
        enabled_modules = [segment.strip() for segment in enabled_modules.split(",") if segment.strip()]
    normalised_modules: List[str] = []
    seen_modules = set()
    for module in enabled_modules:
        if not isinstance(module, str):
            continue
        key = module.strip().lower().replace("_", "-")
        if not key or key in seen_modules:
            continue
        seen_modules.add(key)
        normalised_modules.append(key)
    beta = BetaSettings(
        enabled_modules=tuple(normalised_modules),
        config=dict(beta_conf.get("config", {})),
    )

    ui_conf = config.get("ui", {})
    try:
        preview_speed = float(ui_conf.get("theme_preview_speed", 12.0))
    except (TypeError, ValueError):
        preview_speed = 12.0
    preview_speed = max(0.5, min(preview_speed, 60.0))
    ui = UISettings(theme_preview_speed=preview_speed)

    # Resolve any relative paths relative to base_dir.
    paths = PathsSettings(
        configs={vendor: str((base_dir / Path(rel)).resolve()) for vendor, rel in paths.configs.items()},
        themes_dir=str((base_dir / Path(paths.themes_dir)).resolve())
        if not Path(paths.themes_dir).is_absolute()
        else paths.themes_dir,
        cache_dir=(
            str((base_dir / Path(paths.cache_dir)).resolve())
            if paths.cache_dir and not Path(paths.cache_dir).is_absolute()
            else paths.cache_dir
        ),
        settings_file=str(settings_path),
    )

    return Settings(server=server, paths=paths, features=features, beta=beta, ui=ui)
