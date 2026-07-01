# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
"""Unified config loader with automatic vendor detection.

This module provides a high-level interface for loading firewall configurations
with automatic vendor detection, eliminating the need to specify vendor manually.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional, Tuple, Union, TYPE_CHECKING

from parsers.detector import detect_vendor

__all__ = [
    "ConfigLoadError",
    "load_config",
    "load_config_to_ir",
    "get_engine",
    "get_engine_from_text",
]

# Import types for type checking
if TYPE_CHECKING:
    from parsers.cisco.asa.parser import ASAConfig
    from parsers.fortigate.config import FTGConfig
    _AnyConfig = Union[ASAConfig, FTGConfig]


class ConfigLoadError(Exception):
    """Raised when configuration loading or parsing fails."""
    pass


def get_engine(
    vendor: str,
    text: str,
    use_external_engines: bool = False,
    vdom: Optional[str] = None
) -> _AnyConfig:
    """Internal helper to instantiate the parsing engine.

    The parsers are ciscoconfparse2-backed (a core dependency), so there is a
    single engine per vendor. ``use_external_engines`` is accepted but ignored —
    retained only so existing callers keep working; it will be removed.

    Args:
        vendor: 'asa' or 'fortigate'
        text: Raw configuration text
        use_external_engines: Deprecated no-op (single engine).
        vdom: Optional FortiGate VDOM

    Returns:
        Config object (ASAConfig or FTGConfig).

    Raises:
        ConfigLoadError: If the vendor is unsupported or not yet implemented.
    """
    vendor = vendor.lower()
    if vendor == 'asa':
        from parsers.cisco.asa.parser import ASAConfig
        return ASAConfig(text)

    elif vendor == 'fortigate':
        from parsers.fortigate.config import FTGConfig
        return FTGConfig(text, vdom=vdom)

    elif vendor in ('ios', 'ios-xe', 'ios-xr'):
        raise ConfigLoadError(f"Vendor {vendor} detected but parser not yet implemented")

    raise ConfigLoadError(f"Unsupported vendor: {vendor}")


def get_engine_from_text(
    text: str,
    vendor: Optional[str] = None,
    vdom: str = "",
    filename: str = "",
    min_confidence: int = 60,
    strict: bool = False,
    use_external_engines: bool = False,
) -> Tuple[_AnyConfig, str, int]:
    """Parse already-read config *text* (no file/stdin read) into an engine.

    This is the single in-memory ingestion entry point. Callers that already
    hold config text (the web handlers, the indexer) should use this instead of
    constructing ``ASAConfig``/``FTGConfig`` directly, so vendor detection and
    engine selection stay consistent in one place.

    Args:
        text: Raw configuration text (already read from disk/stdin).
        vendor: Optional vendor override ('asa', 'fortigate'). If None, auto-detect.
        vdom: FortiGate VDOM name (only used if vendor is fortigate).
        filename: Optional filename hint used only to aid auto-detection.
        min_confidence: Minimum confidence score for auto-detection (0-100).
        strict: If True, raise on low confidence. If False, warn and best-guess.
        use_external_engines: Deprecated no-op (ciscoconfparse2 is the single engine).

    Returns:
        Tuple of (config_object, resolved_vendor, confidence_score).

    Raises:
        ConfigLoadError: If detection fails, confidence is too low in strict
            mode, or the engine fails to parse.
    """
    if vendor is None:
        detected_vendor, confidence, reason = detect_vendor(text, filename)

        if detected_vendor == 'unknown':
            hint = f" for {filename}" if filename else ""
            raise ConfigLoadError(
                f"Unable to detect vendor{hint}. "
                f"Please specify vendor explicitly with --vendor"
            )

        if confidence < min_confidence:
            msg = f"Low confidence vendor detection: {detected_vendor} ({confidence}%, reason: {reason})"
            if strict:
                raise ConfigLoadError(msg + ". Use --vendor to override or lower min_confidence.")
            print(f"Warning: {msg}", file=sys.stderr)

        vendor = detected_vendor
    else:
        vendor = vendor.lower()
        confidence = 100  # User-specified, assume 100% confidence

    try:
        cfg = get_engine(
            vendor, text, use_external_engines=use_external_engines, vdom=vdom
        )
        return cfg, vendor, confidence
    except ConfigLoadError:
        raise
    except Exception as e:
        raise ConfigLoadError(f"Failed to parse {vendor} config: {e}") from e


def load_config(
    source: Union[str, Path],
    vendor: Optional[str] = None,
    vdom: str = "",
    min_confidence: int = 60,
    strict: bool = False,
    use_external_engines: bool = False
) -> Tuple[_AnyConfig, str, int]:
    """Load firewall config with automatic vendor detection.

    Args:
        source: Path to config file or "-" for stdin
        vendor: Optional vendor override ('asa', 'fortigate'). If None, auto-detect.
        vdom: FortiGate VDOM name (only used if vendor is fortigate)
        min_confidence: Minimum confidence score for auto-detection (0-100)
        strict: If True, raise error on low confidence. If False, use best guess.
        use_external_engines: Deprecated no-op (ciscoconfparse2 is the single engine).

    Returns:
        Tuple of (config_object, detected_vendor, confidence_score)

    Raises:
        ConfigLoadError: If loading fails or confidence too low

    Examples:
        >>> cfg, vendor, score = load_config("firewall.conf")
        >>> print(f"Detected {vendor} with {score}% confidence")

        >>> # Force specific vendor
        >>> cfg, vendor, score = load_config("firewall.conf", vendor="asa")

        >>> # Strict mode requires high confidence
        >>> cfg, vendor, score = load_config("mystery.conf", strict=True, min_confidence=80)
    """
    # Read config text
    if source == "-":
        text = sys.stdin.read()
        filename = "stdin"
    else:
        path = Path(source)
        if not path.is_file():
            raise ConfigLoadError(f"File not found: {source}")
        text = path.read_text()
        filename = path.name

    # Detection + engine construction is shared with the in-memory entry point.
    return get_engine_from_text(
        text,
        vendor=vendor,
        vdom=vdom,
        filename=filename,
        min_confidence=min_confidence,
        strict=strict,
        use_external_engines=use_external_engines,
    )


def load_config_to_ir(
    source: Union[str, Path],
    vendor: Optional[str] = None,
    device_name: Optional[str] = None,
    vdom: str = "",
    use_external_engines: bool = False,
    **kwargs
):
    """Load config and immediately convert to IR.

    This is a convenience function that combines load_config() with IR export.

    Args:
        source: Path to config file or "-" for stdin
        vendor: Optional vendor override
        device_name: Device name for IR (defaults to filename)
        vdom: FortiGate VDOM
        use_external_engines: Deprecated no-op (ciscoconfparse2 is the single engine).
        **kwargs: Additional args passed to load_config()

    Returns:
        IR Device object

    Example:
        >>> from parsers.loader import load_config_to_ir
        >>> device = load_config_to_ir("firewall.conf")
        >>> print(f"{device.vendor} v{device.version}: {len(device.acls)} ACLs")
    """
    cfg, detected_vendor, _ = load_config(
        source, vendor=vendor, vdom=vdom,
        use_external_engines=use_external_engines, **kwargs
    )

    # Determine device name
    if device_name is None:
        if source == "-":
            device_name = "stdin"
        else:
            device_name = Path(source).stem

    # Export to IR based on vendor
    if detected_vendor == 'asa':
        from parsers.cisco.asa import ir_export
        return ir_export.to_ir(cfg, device_name=device_name)
    elif detected_vendor == 'fortigate':
        from parsers.fortigate import ir_export
        return ir_export.to_ir(cfg, device_name=device_name)
    else:
        raise ConfigLoadError(f"IR export not implemented for {detected_vendor}")
