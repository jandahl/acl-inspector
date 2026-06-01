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

# Import types for type checking
if TYPE_CHECKING:
    from parsers.cisco.asa.parser import ASAConfig
    from parsers.fortigate.config import FTGConfig

__all__ = ["load_config", "load_config_to_ir", "ConfigLoadError"]


class ConfigLoadError(Exception):
    """Raised when config loading fails."""
    pass


def load_config(
    source: Union[str, Path],
    vendor: Optional[str] = None,
    vdom: str = "",
    min_confidence: int = 60,
    strict: bool = False,
    use_external_engines: bool = False
) -> Tuple[Union["ASAConfig", "FTGConfig", Any], str, int]:
    """Load firewall config with automatic vendor detection.

    Args:
        source: Path to config file or "-" for stdin
        vendor: Optional vendor override ('asa', 'fortigate'). If None, auto-detect.
        vdom: FortiGate VDOM name (only used if vendor is fortigate)
        min_confidence: Minimum confidence score for auto-detection (0-100)
        strict: If True, raise error on low confidence. If False, use best guess.
        use_external_engines: If True, use parallel advanced parsing engines.

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

    # Auto-detect vendor if not specified
    if vendor is None:
        detected_vendor, confidence, reason = detect_vendor(text, filename)

        if detected_vendor == 'unknown':
            raise ConfigLoadError(
                f"Unable to detect vendor for {filename}. "
                f"Please specify vendor explicitly with --vendor"
            )

        if confidence < min_confidence:
            msg = f"Low confidence vendor detection: {detected_vendor} ({confidence}%, reason: {reason})"
            if strict:
                raise ConfigLoadError(msg + ". Use --vendor to override or lower min_confidence.")
            else:
                print(f"Warning: {msg}", file=sys.stderr)

        vendor = detected_vendor
    else:
        vendor = vendor.lower()
        confidence = 100  # User-specified, assume 100% confidence
        reason = "user_specified"

    # Parse config based on vendor
    if vendor == 'asa':
        if use_external_engines:
            from parsers.cisco.asa.advanced_parser import AdvancedASAConfig
            try:
                cfg = AdvancedASAConfig(text)
                return cfg, vendor, confidence
            except ImportError as e:
                raise ConfigLoadError(f"External engine error: {e}. Try: pip install .[external]")
            except Exception as e:
                raise ConfigLoadError(f"Failed to parse ASA config with advanced engine: {e}")

        from parsers.cisco.asa.parser import ASAConfig
        try:
            cfg = ASAConfig(text)
            return cfg, vendor, confidence
        except Exception as e:
            raise ConfigLoadError(f"Failed to parse ASA config: {e}")

    elif vendor == 'fortigate':
        if use_external_engines:
            from parsers.fortigate.advanced_parser import AdvancedFTGConfig
            try:
                cfg = AdvancedFTGConfig(text, vdom=vdom)
                return cfg, vendor, confidence
            except ImportError as e:
                raise ConfigLoadError(f"External engine error: {e}. Try: pip install .[external]")
            except Exception as e:
                raise ConfigLoadError(f"Failed to parse FortiGate config with advanced engine: {e}")

        from parsers.fortigate.config import FTGConfig
        try:
            cfg = FTGConfig(text, vdom=vdom)
            return cfg, vendor, confidence
        except Exception as e:
            raise ConfigLoadError(f"Failed to parse FortiGate config: {e}")

    elif vendor in ('ios', 'ios-xe', 'ios-xr'):
        raise ConfigLoadError(f"Vendor {vendor} detected but parser not yet implemented")

    else:
        raise ConfigLoadError(f"Unsupported vendor: {vendor}")


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
        use_external_engines: If True, use parallel advanced parsing engines.
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
