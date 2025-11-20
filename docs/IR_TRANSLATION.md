# IR Translation Guide

This document describes the Intermediate Representation (IR) translation feature in ACL-inspector, which enables cross-vendor firewall configuration migration and analysis.

## Overview

The IR translation system provides a vendor-agnostic representation of firewall configurations that enables:

- **Round-trip validation**: ASA→IR→ASA and FortiGate→IR→FortiGate
- **Cross-vendor migration**: ASA↔FortiGate bidirectional translation
- **Configuration analysis**: Export to JSON for inspection and comparison

## Architecture

```
┌─────────┐           ┌────────┐           ┌────────────┐
│   ASA   │──export──→│   IR   │──import──→│ FortiGate  │
│ Config  │           │ (JSON) │           │   Config   │
└─────────┘           └────────┘           └────────────┘
     ↑                                             │
     └─────────────round-trip──────────────────────┘
```

### IR Schema (parsers/model.py)

The IR schema is versioned and designed to be:
- **Vendor-agnostic**: Normalizes vendor-specific concepts
- **JSON-serializable**: All data types convert cleanly to JSON
- **Extensible**: New fields can be added without breaking existing code

Core data structures:
- `Device`: Top-level container (vendor, version, interfaces, objects, groups, ACLs, NAT)
- `Object`: Network objects with IP literals
- `Group`: Object groups with nested members
- `ServiceGroup`: Service/port definitions
- `ACL`: Access control lists with flattened entries
- `NAT`: NAT rules (both auto and manual)
- `Interface`: Interface definitions with zones/security-levels

## CLI Usage

### Basic Translation

Translate ASA config to FortiGate:
```bash
./aclinspector.py inspect \
  --vendor asa \
  --config asa-firewall.conf \
  --translate \
  --target-vendor fortigate \
  > fortigate-output.conf
```

Translate FortiGate config to ASA:
```bash
./aclinspector.py inspect \
  --vendor fortigate \
  --config fortigate.conf \
  --translate \
  --target-vendor asa \
  > asa-output.conf
```

### Export to JSON (IR inspection)

View the intermediate representation as JSON:
```bash
./aclinspector.py inspect \
  --vendor asa \
  --config asa-firewall.conf \
  --translate \
  --target-vendor fortigate \
  --format json \
  > config.ir.json
```

### Device Naming

Specify a device name for the IR export:
```bash
./aclinspector.py inspect \
  --vendor asa \
  --config fw01.conf \
  --translate \
  --target-vendor fortigate \
  --device-name "fw01-dc1"
```

### VDOM Handling (FortiGate)

When working with FortiGate VDOMs:
```bash
# Export specific VDOM
./aclinspector.py inspect \
  --vendor fortigate \
  --config multi-vdom.conf \
  --vdom "production" \
  --translate \
  --target-vendor asa

# Import to specific VDOM
./aclinspector.py inspect \
  --vendor asa \
  --config asa.conf \
  --translate \
  --target-vendor fortigate \
  --vdom "production"
```

## Translation Coverage

### Currently Supported

#### ASA → IR → FortiGate
- ✅ Network objects (`object network` → `config firewall address`)
- ✅ Object groups (`object-group network` → `config firewall addrgrp`)
- ✅ Service groups (partial, see limitations)
- ✅ Access lists (flattened to policies)
- ✅ Static routes (`route` → `config router static`)
- ✅ OSPF configuration (`router ospf` → `config router ospf`)
- ✅ BGP configuration (`router bgp` → `config router bgp`)
- ✅ EIGRP configuration (parsed but FortiGate has no direct equivalent)

#### FortiGate → IR → ASA
- ✅ Firewall addresses (`config firewall address` → `object network`)
- ✅ Address groups (`config firewall addrgrp` → `object-group network`)
- ✅ Service custom/groups → ASA service object-groups
- ✅ Policies → Access lists
- ✅ Static routes (`config router static` → `route`)
- ✅ OSPF configuration (`config router ospf` → `router ospf`)
- ✅ BGP configuration (`config router bgp` → `router bgp`)

### Current Limitations

1. **Service objects**: ASA parser doesn't yet parse `port-object`/`service-object` lines
2. **NAT rules**: Translation implemented in IR but not fully tested
3. **Interfaces**: Minimal interface mapping (FortiGate zones vs ASA interfaces)
4. **Dynamic routing features**: Advanced features like route-maps, prefix-lists, and policy-based routing not yet supported
5. **RIP/EIGRP on FortiGate**: FortiGate doesn't support RIP/EIGRP in modern versions (OSPF/BGP only)
6. **VPN/Crypto**: Out of scope for initial release

## Round-Trip Validation

The translation system includes comprehensive unit tests to ensure configurations survive round-trip conversion:

```bash
# Run IR translation tests
python3 -m unittest tests.test_ir_translation -v
```

Test coverage:
- ASA → IR → ASA (network objects, groups, ACLs)
- FortiGate → IR → FortiGate (addresses, groups, policies, services)
- ASA ↔ FortiGate (cross-vendor translation)
- IR schema stability (JSON serialization, versioning)

## Routing Translation Examples

### Static Routes

ASA static route with tracking:
```bash
route outside 0.0.0.0 0.0.0.0 203.0.113.1 1 track 10
```

Translates to FortiGate:
```
config router static
    edit 1
        set dst 0.0.0.0/0
        set gateway 203.0.113.1
        set device "outside"
        set distance 1
    next
end
```

### OSPF Configuration

ASA OSPF config:
```bash
router ospf 1
 router-id 1.1.1.1
 network 192.168.1.0 255.255.255.0 area 0
 network 192.168.2.0 255.255.255.0 area 1
 log-adjacency-changes
```

Translates to FortiGate:
```
config router ospf
    set router-id 1.1.1.1
    config network
        edit 1
            set prefix 192.168.1.0
            set area 0
        next
        edit 2
            set prefix 192.168.2.0
            set area 1
        next
    end
end
```

### BGP Configuration

FortiGate BGP config:
```
config router bgp
    set as 65001
    set router-id 10.10.10.10
    config neighbor
        edit "203.0.113.100"
            set remote-as 65002
        next
    end
end
```

Translates to ASA:
```
router bgp 65001
 router-id 10.10.10.10
 neighbor 203.0.113.100 remote-as 65002
```

## Example Workflows

### Migration Analysis

1. **Convert ASA to FortiGate**:
   ```bash
   ./aclinspector.py inspect --vendor asa --config old-asa.conf \
     --translate --target-vendor fortigate > new-fortigate.conf
   ```

2. **Validate by reverse translation**:
   ```bash
   ./aclinspector.py inspect --vendor fortigate --config new-fortigate.conf \
     --translate --target-vendor asa > reverse-asa.conf
   ```

3. **Compare original vs reverse**:
   ```bash
   diff -u old-asa.conf reverse-asa.conf
   ```

### Policy Comparison

Export both configs to IR JSON and compare:
```bash
./aclinspector.py inspect --vendor asa --config fw1.conf \
  --translate --target-vendor fortigate --format json > fw1.ir.json

./aclinspector.py inspect --vendor fortigate --config fw2.conf \
  --translate --target-vendor asa --format json > fw2.ir.json

# Use jq to compare specific fields
jq '.acls' fw1.ir.json > fw1-acls.json
jq '.acls' fw2.ir.json > fw2-acls.json
diff -u fw1-acls.json fw2-acls.json
```

## Implementation Details

### Module Structure

- `parsers/model.py`: IR schema definitions
- `parsers/cisco/asa/ir_export.py`: ASA → IR conversion
- `parsers/cisco/asa/ir_import.py`: IR → ASA conversion
- `parsers/fortigate/ir_export.py`: FortiGate → IR conversion
- `parsers/fortigate/ir_import.py`: IR → FortiGate conversion

### Adding New Vendors

To add support for a new vendor:

1. Create `parsers/<vendor>/ir_export.py`:
   ```python
   def to_ir(cfg: VendorConfig, device_name: str = None) -> ir.Device:
       # Convert vendor config to IR
       pass
   ```

2. Create `parsers/<vendor>/ir_import.py`:
   ```python
   def from_ir(device: ir.Device) -> str:
       # Convert IR to vendor config syntax
       pass
   ```

3. Add CLI integration in `cli/access-list-inspector.py`
4. Write round-trip tests in `tests/test_ir_translation.py`

## Future Enhancements

- **NAT rule translation**: Full coverage of ASA and FortiGate NAT syntax
- **Interface mapping**: Better zone/interface translation
- **Service object parsing**: Complete ASA service object-group support
- **Policy optimization**: Detect and merge duplicate/overlapping rules
- **Diff mode**: Show semantic differences between configs post-translation
- **Additional vendors**: Palo Alto, Juniper SRX, pfSense

## Troubleshooting

### Translation produces unexpected output

Check the IR JSON to see how the config was parsed:
```bash
./aclinspector.py inspect --vendor asa --config test.conf \
  --translate --target-vendor fortigate --format json | jq .
```

### Round-trip doesn't match original

This is expected for some syntactic differences:
- ASA uses netmasks (`255.255.255.0`), IR uses CIDR (`/24`)
- FortiGate has different service syntax than ASA
- Order of definitions may change

Focus on semantic equivalence, not syntactic identity.

### Missing objects in translation

Ensure source config defines objects before they're referenced:
- Network objects before object-groups
- Object-groups before ACLs
- Service objects before service groups

## References

- IR Schema: `parsers/model.py`
- ASA Export: `parsers/cisco/asa/ir_export.py`
- FortiGate Export: `parsers/fortigate/ir_export.py`
- Unit Tests: `tests/test_ir_translation.py`
- Example Configs: `tests/fixtures/configs/`
