# Firewall Parsers

The `parsers` directory provides modular, vendor-agnostic ingestion for firewall configurations. The goal of these parsers is to process a raw text configuration file (Cisco ASA, FortiGate, etc.) and convert it into a consistent **Intermediate Representation (IR)**.

Other scripts, tools, and platforms can use these parsers independently of the main `aclinspector` UI or CLI to perform their own analysis, graph generation, or cross-vendor migrations.

## Getting Started

The recommended way to interact with the parsers is through the unified loader (`parsers.loader`). It automatically handles vendor detection, instantiates the correct underlying parser, and exposes both the native configuration object and the standardized IR.

### 1. Unified Loader (Auto-Detection)

Use `load_config` to parse a file while automatically detecting the vendor format. It returns the vendor-specific config object, the detected vendor name, and a confidence score (0-100).

```python
from parsers.loader import load_config, ConfigLoadError

try:
    # `cfg` is the vendor-specific config object (e.g. ASAConfig or FTGConfig)
    # `vendor` is a string (e.g., 'asa', 'fortigate')
    # `score` is the confidence level of the detection (0-100)
    cfg, vendor, score = load_config("path/to/firewall.conf")
    print(f"Loaded {vendor} configuration (Confidence: {score}%)")
    
    # Optional parameters:
    # - vdom: Select a specific FortiGate VDOM
    # - vendor: Override auto-detection (e.g., vendor="asa")
    # - strict: If True, raises error if detection is ambiguous
    # - min_confidence: Minimum score (default 40) required to proceed
    
except ConfigLoadError as e:
    print(f"Failed to load config: {e}")
```

### 2. Loading Directly to IR (Recommended)
If your goal is cross-vendor portability, you likely want to work with the **Intermediate Representation (IR)** rather than the vendor-specific syntax tree. The IR provides standard python dataclasses for Interfaces, Objects, Groups, ACLs, NATs, and Routing Protocols.

Note: `load_config_to_ir` may raise `ConfigLoadError` if the vendor is detected but not yet supported by the IR pipeline (e.g., legacy IOS).

```python
import json
from parsers.loader import load_config_to_ir, ConfigLoadError

try:
    # Automatically detect vendor, parse the file, and convert to an IR Device.
    # Specify 'device_name' to override the default (filename stem).
    ir_device = load_config_to_ir("path/to/firewall.conf", device_name="FW-CORE-01")

    print(f"Device Name: {ir_device.name or 'unknown'}")
    print(f"Vendor: {ir_device.vendor}")
    print(f"Total Network Objects: {len(ir_device.objects)}")
    print(f"Total ACLs: {len(ir_device.acls)}")
    
    # Optional parameters (same as load_config):
    # - vdom, vendor, strict, min_confidence

    # The IR can be safely serialized to JSON:
    with open("firewall_ir.json", "w", encoding="utf-8") as f:
        json.dump(ir_device.to_dict(), f, indent=2)

except ConfigLoadError as e:
    print(f"Failed to load config: {e}")
```

## The Intermediate Representation (IR)

The IR is defined in `parsers/model.py`. All vendors map their internal models down to these standard dataclasses. By depending on the IR, your script won't need to be rewritten when support for a new vendor is added.

Key models include:

- **`Device`**: The root container for the firewall configuration.
- **`Object`**: Network objects mapping to IP literals/networks.
- **`Group`**: Groups containing nested objects, literals, or other groups.
- **`ACL` & `ACLEntry`**: Access Control Lists with standardized source, destination, protocol, and action fields.
- **`NAT`**: Normalized NAT tables and endpoints.
- **`StaticRoute` / `DynamicRoutingProcess`**: BGP, OSPF, and static route definitions.

## Direct Vendor Parsers

If you know the exact vendor and want access to native parsing structures (e.g., for generating a vendor-specific optimization report), you can bypass the `loader` and initialize the parsers directly:

### Cisco ASA

```python
from parsers.cisco.asa.parser import ASAConfig

with open("asa.conf", encoding="utf-8") as f:
    config = ASAConfig(f.read())

# Access raw vendor methods
print(f"ASA Objects: {len(config.network_objects)}")
print(f"ASA Object Groups: {len(config.network_object_groups)}")

# Or extract the flattened rules directly:
flat_rules = config.flatten_acl()
for rule in flat_rules[:5]:
    # rules are returned as dictionaries
    print(f"{rule['action']} {rule['proto']}")
```

### FortiGate

```python
from parsers.fortigate.config import FTGConfig

with open("fortigate.conf", encoding="utf-8") as f:
    # Note: FortiGate configurations often utilize Virtual Domains (VDOMs).
    # Specify the target vdom, or omit it (auto-selects the first VDOM if present).
    # For multi-VDOM configs, pass vdom="root" (or other name) to target specifically.
    config = FTGConfig(f.read())

flat_rules = config.flatten_policies()
```

## Adding a New Vendor

If you are extending the framework to support a new firewall platform (e.g., Palo Alto, CheckPoint):

1. **Implement IR Export (Primary)**: The core integration point for ACL Inspector is the Intermediate Representation. Provide a `to_ir(cfg, ...)` function in an `ir_export.py` module that maps your parsed configuration class down to the dataclasses in `parsers/model.py`.
2. **Implement Flat Rules (Optional)**: If you wish to support the legacy inspection views, implement a flattening method. For new parsers inheriting from `FirewallParser`, implement `flatten() -> List[FlatRule]`. For legacy-style parsers, implement `flatten_acl()` or `flatten_policies()` returning a `List[dict]`.
3. **Register the Detection**: Add detection heuristics to `_detect_vendor` in `scripts/index_repo.py`. You must also update `_vendor_to_os`, `_build_index`, and `DEFAULT_SUPPORTED_VENDORS` in the same file to fully integrate the new vendor. While `parsers/loader.py` imports the detection function dynamically at runtime (via a `sys.path` injection), you must also manually add dispatch branches to `load_config()` and `load_config_to_ir()` inside `parsers/loader.py` to support the new vendor string.

> **Note on Coupling**: The dynamic import of `scripts/index_repo.py` by the parser loader is a known architectural coupling intended for internal development. A future refactor will move the core detection logic into the `parsers/` package for cleaner library use.

> **Note on Architecture**: While existing production parsers (`ASAConfig`, `FTGConfig`) currently use custom methods for historical reasons, new modular components are encouraged to inherit from `FirewallParser` (defined in `parsers/base.py`) to move towards a more consistent interface.
