#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
# Copyright (c) 2024-2026 Jan Gronemann
"""Manual test to verify tabs show actual data."""

import sys
from pathlib import Path

from parsers.cisco.asa.parser import ASAConfig
from analysis_core import inspect_object, compare_objects, find_object_usage

# Load test config
config_path = "configs/cisco/cisco-asa-example"
with open(config_path, 'r') as f:
    config_text = f.read()

config = ASAConfig(config_text)

print("="*80)
print("Testing Tabs with Real Data")
print("="*80)

# List available objects
print("\nAvailable objects:")
for i, (obj_name, networks) in enumerate(list(config.network_objects.items())[:10]):
    print(f"  {i+1}. {obj_name}: {list(networks)[:2]}")

# Test 1: Inspect Tab
print("\n" + "="*80)
print("TEST 1: INSPECT TAB")
print("="*80)
test_obj = list(config.network_objects.keys())[0]
print(f"Inspecting: {test_obj}")

try:
    result = inspect_object(config, test_obj, include_any=False)
    print(f"\nInspect Result:")
    print(f"  Object: {result.object_name}")
    print(f"  Resolved to: {result.resolved_addresses[:5]}")
    print(f"  Matching rules: {result.total_rules}")
    print(f"  Rules found: {len(result.matching_rules)}")

    if result.matching_rules:
        print(f"\nFirst few rules:")
        for rule in result.matching_rules[:3]:
            print(f"    ACL: {rule.get('acl', 'N/A')}")
            print(f"    Action: {rule.get('action', 'N/A')}")
            print(f"    Raw: {rule.get('raw', 'N/A')[:80]}")
            print()
    else:
        print("  WARNING: No matching rules found!")
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()

# Test 2: Compare Tab
print("\n" + "="*80)
print("TEST 2: COMPARE TAB")
print("="*80)
obj_list = list(config.network_objects.keys())
if len(obj_list) >= 2:
    obj1, obj2 = obj_list[0], obj_list[1]
    print(f"Comparing: {obj1} vs {obj2}")

    try:
        result = compare_objects(config, obj1, obj2, include_any=False)
        print(f"\nCompare Result:")
        print(f"  Old: {result.old_name}")
        print(f"  New: {result.new_name}")
        print(f"  Old-only rules: {len(result.old_only_rules)}")
        print(f"  New-only rules: {len(result.new_only_rules)}")
        print(f"  Common rules: {len(result.common_rules)}")

        if result.old_only_rules:
            print(f"\n  First removed rule:")
            rule = result.old_only_rules[0]
            print(f"    {rule.get('action', 'N/A')}: {rule.get('raw', 'N/A')[:80]}")
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
else:
    print("Not enough objects to compare")

# Test 3: Used in ACLs Tab
print("\n" + "="*80)
print("TEST 3: USED IN ACLs TAB")
print("="*80)
print(f"Finding usage of: {test_obj}")

try:
    result = find_object_usage(config, test_obj)
    print(f"\nUsage Result:")
    print(f"  Object: {result.object_name}")
    print(f"  Found in ACLs: {len(result.acl_references)}")
    print(f"  Found in groups: {len(result.group_references)}")

    if result.acl_references:
        print(f"\n  ACL References:")
        for acl_ref in result.acl_references[:5]:
            print(f"    ACL: {acl_ref.get('acl_name', 'N/A')}")
            print(f"    Position: {acl_ref.get('position', 'N/A')}")
    else:
        print("  WARNING: No ACL references found!")

    if result.group_references:
        print(f"\n  Group References:")
        for group in result.group_references[:5]:
            print(f"    Group: {group}")
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "="*80)
print("Test Complete")
print("="*80)
