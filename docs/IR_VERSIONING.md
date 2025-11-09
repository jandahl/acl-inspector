# IR Schema Versioning Strategy

## Overview

The Intermediate Representation (IR) schema in `parsers/model.py` uses a versioned approach to ensure stability and backward compatibility as the project evolves. This document describes the versioning strategy, evolution guidelines, and migration patterns.

## Version Tracking

The current IR version is tracked by the `IR_VERSION` constant in `parsers/model.py`:

```python
IR_VERSION = "1.0"  # Current version
```

Every `Device` object automatically includes this version:

```python
device = ir.Device(
    vendor='asa',
    version='9.8',
    ir_version=IR_VERSION,  # Automatically set
    # ...
)
```

## Versioning Scheme

ACL-inspector uses **semantic versioning** for the IR schema:

- **Major version** (X.0): Breaking changes that require migration
  - Removing fields
  - Changing field types incompatibly (e.g., string → int)
  - Restructuring nested data shapes
  - Changing semantics of existing fields

- **Minor version** (1.X): Additive changes that are backward compatible
  - Adding new optional fields
  - Adding new dataclasses
  - Expanding allowed values in enums
  - Adding new vendor support

## Current Schema (v1.0)

### Core Dataclasses

**Device** (root container):
- `vendor`: str - Vendor identifier ('asa', 'fortigate', etc.)
- `os`: str - Operating system ('ASA', 'FortiOS')
- `version`: str - Software version
- `ir_version`: str - IR schema version (default: current `IR_VERSION`)
- `name`: Optional[str] - Device hostname
- `interfaces`: List[Interface]
- `objects`: List[Object]
- `groups`: List[Group]
- `service_groups`: List[ServiceGroup]
- `acls`: List[ACL]
- `nats`: List[NAT]
- `static_routes`: List[StaticRoute]
- `dynamic_routing`: List[DynamicRoutingProcess]
- `routes`: List[Route] - **Deprecated** (use `static_routes`)

**Object** (network objects):
- `name`: str
- `literals`: List[str] - IP addresses/networks in string format

**Group** (network object groups):
- `name`: str
- `members`: List[GroupMember] - Group member references

**GroupMember**:
- `kind`: str - 'object' | 'group' | 'literal'
- `ref`: Optional[str] - Referenced object/group name
- `literal`: Optional[str] - Direct IP literal

**ServiceGroup**:
- `name`: str
- `members`: List[Dict[str, Any]] - Service definitions or references

**ACL** (access control list):
- `name`: str
- `bound_to`: Optional[str] - Interface/zone binding
- `entries`: List[ACLEntry]
- `binding`: Optional[Dict[str, Any]] - Full binding metadata

**ACLEntry**:
- `action`: str - 'permit' | 'deny'
- `proto`: Optional[str]
- `src`: List[str] - Source addresses
- `dst`: List[str] - Destination addresses
- `svc`: Dict[str, Any] - Service/port specification
- `raw`: str - Original config line
- `acl`: Optional[str] - Parent ACL name
- `bound_to`: Optional[str] - Interface binding
- `binding`: Optional[Dict[str, Any]] - Binding metadata
- `direction`: Optional[str] - 'in' | 'out' | 'global' | 'control-plane'

**NAT**:
- `kind`: str - 'auto' | 'manual'
- `src_if`: Optional[str]
- `dst_if`: Optional[str]
- `section`: Optional[int]
- `detail`: Dict[str, Any] - NAT-specific details
- `raw`: Optional[str]

**StaticRoute**:
- `destination`: str - CIDR notation
- `next_hop`: Optional[str]
- `interface`: Optional[str]
- `distance`: Optional[int] - Administrative distance
- `metric`: Optional[int]
- `track`: Optional[int] - Track object ID
- `tunneled`: Optional[bool] - VPN route flag

**DynamicRoutingProcess**:
- `protocol`: str - 'ospf' | 'eigrp' | 'bgp' | 'rip'
- `process_id`: Optional[str] - Process ID or AS number
- `router_id`: Optional[str]
- `networks`: List[Dict[str, Any]] - Advertised networks
- `neighbors`: List[Dict[str, Any]] - BGP neighbors
- `redistribute`: List[Dict[str, Any]] - Redistribution config
- `passive_interfaces`: List[str]
- `areas`: List[Dict[str, Any]] - **Deprecated** (use `areas_config`)
- `areas_config`: Dict[str, Dict[str, Any]] - OSPF area configuration
- `timers`: Dict[str, Any] - Protocol timers
- `authentication`: Dict[str, Any]
- `distance`: Dict[str, Any]
- `config`: Dict[str, Any] - Additional protocol-specific config

**Interface**:
- `name`: str
- `physical`: Optional[str] - Physical interface name
- `ipv4`: Optional[str] - IP address in CIDR
- `security_level`: Optional[int] - ASA security level

**FlowContext** (packet flow evaluation):
- `src_ip`: str
- `dst_ip`: str
- `proto`: Optional[str]
- `src_port`: Optional[int]
- `dst_port`: Optional[int]
- `ingress_zone`: Optional[str]
- `egress_zone`: Optional[str]
- `flow_direction`: Optional[str]
- `applicable_policies`: List[str]
- `applicable_nats`: List[str]
- `route_matched`: Optional[str]
- `next_hop`: Optional[str]
- `vendor_context`: Dict[str, Any]

## Evolution Guidelines

### Adding New Fields (Minor Version Bump)

When adding new optional fields, follow this pattern:

```python
@dataclass
class Object:
    name: str
    literals: List[str] = field(default_factory=list)
    # New field in v1.1
    description: Optional[str] = None  # ALWAYS optional with default
```

**Requirements:**
- New fields MUST be optional (use `Optional[T]` or provide a default)
- Document the version when the field was added
- Update IR_TRANSLATION.md with the new field
- Add unit tests covering the new field
- Update vendor export/import modules to handle the field

### Deprecating Fields (No Version Change)

Mark deprecated fields with a comment and plan removal for next major version:

```python
@dataclass
class Device:
    # ...
    routes: List[Route] = field(default_factory=list)  # DEPRECATED in v1.0, use static_routes
```

**Process:**
1. Add deprecation comment
2. Keep field functional
3. Update documentation to guide users to replacement
4. Remove in next major version (v2.0)

### Breaking Changes (Major Version Bump)

When making incompatible changes:

1. **Bump IR_VERSION**: Change `IR_VERSION = "2.0"`
2. **Create migration function**:
   ```python
   def migrate_v1_to_v2(device_dict: dict) -> dict:
       """Migrate IR v1.0 Device to v2.0."""
       # Handle field removals, renames, type changes
       return migrated_dict
   ```
3. **Update all vendor modules**: Ensure export/import functions work with v2.0
4. **Add migration tests**: Test round-trip through migration
5. **Document breaking changes**: Update CHANGELOG and migration guide

## Version Detection and Migration

### Detecting IR Version

When loading IR from JSON:

```python
import json
from parsers import model as ir

with open('config.ir.json') as f:
    data = json.load(f)

ir_version = data.get('ir_version', '1.0')  # Default to 1.0 if missing

if ir_version != ir.IR_VERSION:
    print(f"Warning: IR version mismatch (file: {ir_version}, current: {ir.IR_VERSION})")
```

### Migration Pattern

```python
def load_device(data: dict) -> ir.Device:
    """Load Device from dict, applying migrations if needed."""
    ir_version = data.get('ir_version', '1.0')

    # Apply migrations in sequence
    if ir_version == '1.0' and ir.IR_VERSION == '2.0':
        data = migrate_v1_to_v2(data)
    elif ir_version == '2.0' and ir.IR_VERSION == '3.0':
        data = migrate_v2_to_v3(data)

    # Construct from migrated data
    return ir.Device(**data)
```

## JSON Serialization

The IR uses `_jsonable()` helper to ensure clean JSON export:

- Dataclasses are converted to dicts via `asdict()`
- Sets are sorted and converted to lists (deterministic output)
- IP address objects are stringified
- All dict keys are converted to strings

**Example:**

```python
device = asa_export.to_ir(cfg, device_name="fw1")
device_dict = device.to_dict()  # Uses _jsonable() internally

import json
with open('fw1.ir.json', 'w') as f:
    json.dump(device_dict, f, indent=2)
```

## Testing Strategy

### Version Stability Tests

In `tests/test_ir_translation.py`:

```python
def test_ir_version_present(self):
    """Ensure IR version is tracked."""
    device = asa_export.to_ir(cfg)
    self.assertIsNotNone(device.ir_version)
    self.assertEqual(device.ir_version, ir.IR_VERSION)

def test_to_dict_json_serializable(self):
    """Ensure IR can be serialized to JSON."""
    device = asa_export.to_ir(cfg)
    device_dict = device.to_dict()
    json_str = json.dumps(device_dict)
    self.assertIsInstance(json_str, str)
```

### Round-Trip Tests

Every vendor should have round-trip tests:

```python
def test_asa_round_trip(self):
    """ASA → IR → ASA preserves semantics."""
    cfg = ASAConfig(asa_config_text)
    device = asa_export.to_ir(cfg)
    output = asa_import.from_ir(device)
    # Verify essential config elements present
```

### Cross-Vendor Tests

Verify cross-vendor translation:

```python
def test_asa_to_fortigate_translation(self):
    """ASA → IR → FortiGate generates valid FortiOS config."""
    cfg = ASAConfig(asa_config)
    device = asa_export.to_ir(cfg)
    ftg_output = ftg_import.from_ir(device)
    # Verify FortiGate syntax
```

## Backward Compatibility Guarantees

**Within same major version (v1.x):**
- JSON generated by older minor version can be loaded by newer version
- New fields are ignored by older parsers (graceful degradation)
- Deprecated fields remain functional until major version bump

**Across major versions (v1.x → v2.x):**
- No automatic compatibility
- Migration functions required
- Breaking changes documented
- Old IR files must be migrated before loading

## Future Enhancements

### Planned for v1.1 (Additive)
- Interface zone mapping (FortiGate VDOM → ASA interface translation)
- VPN/crypto configuration representation
- Advanced NAT features (PAT, policy NAT)
- Route-map and prefix-list support

### Planned for v2.0 (Breaking)
- Remove deprecated `routes` field (use `static_routes`)
- Remove deprecated `areas` field (use `areas_config`)
- Unify service representation across vendors
- Strict typing for nested dicts (convert to dataclasses)

## Best Practices

1. **Always set defaults for new fields** to maintain backward compatibility
2. **Use `Optional[T]` for all vendor-specific fields** that may not apply universally
3. **Document version when fields are added** in docstrings
4. **Test round-trip for every dataclass** to catch serialization issues early
5. **Keep IR vendor-neutral** - avoid vendor-specific field names (e.g., use `zone` not `vdom`)
6. **Preserve raw config** in `raw` fields when available for debugging
7. **Use string types for IDs** (process_id, AS numbers) to handle edge cases

## References

- IR Schema: `parsers/model.py`
- Translation Guide: `docs/IR_TRANSLATION.md`
- Test Suite: `tests/test_ir_translation.py`
- ASA Export: `parsers/cisco/asa/ir_export.py`
- ASA Import: `parsers/cisco/asa/ir_import.py`
- FortiGate Export: `parsers/fortigate/ir_export.py`
- FortiGate Import: `parsers/fortigate/ir_import.py`
