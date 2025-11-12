# TUI Quick Start Guide

## Launch the TUI with Example Config

```bash
./tui/__init__.py --vendor asa --config configs/cisco/cisco-asa-example
```

## Example Walkthrough

### 1. Search for an Object

Type to search: `alpha_lobby`

You'll see results like:
- `alpha_lobby_net` (subnet 10.0.1.0/24)
- `alpha_lobby_host1` (host 10.0.1.101)
- `alpha_lobby_host2` (host 10.0.1.102)

### 2. Select an Object (Try: alpha_dest1_host1)

**Press Enter** on `alpha_dest1_host1`

You'll enter drill-down mode with 5 tabs:

---

## Tab 1: Details Tab (default)

Shows:
```
Name: alpha_dest1_host1
Type: OBJECT
Source: cisco-asa-example
IP Addresses: 10.1.1.101
Total Count: 1
Member of Groups: alpha_dest1_grp
```

**Try Export**: Press `Ctrl+E`
- Select JSON/CSV/TXT format
- Enter filename (or use default)
- File saved to current directory

---

## Tab 2: Inspect Tab

**Press Right Arrow** to switch tabs

Shows all ACL rules that affect this object:

```
Matching ACL Rules:

1. [permit] alpha_lobby_access
   Protocol: tcp  Port: 80
   Source: 10.0.1.0/24 → Destination: 10.1.1.101
   access-list alpha_lobby_access extended permit tcp object alpha_lobby_net object alpha_dest1_host1 eq 80
```

### Try Filtering:
1. In the filter bar at top, enter:
   - Protocol: `tcp`
   - Port: `80`
   - Action: `permit`

2. Click **Apply Filters** or press Enter

3. Results update to show only TCP port 80 permits

**Try Export**: Press `Ctrl+E` to export filtered results

---

## Tab 3: Compare Tab

**Press Right Arrow** again

1. You'll see: "First object: alpha_dest1_host1"
2. Type to search for second object: `alpha_dest1_host2`
3. Press Enter

Shows comparison:
```
Comparing: alpha_dest1_host1 ← → alpha_dest1_host2

Summary:
  Rules only in OLD (removed)      0
  Rules only in NEW (added)        1
  Common rules (unchanged)         1

1 Rules Being Added:
  + [permit] access-list alpha_lobby_access ... alpha_dest1_host2 ...
```

**Try Export**: Press `Ctrl+E` to export comparison

---

## Tab 4: Used in ACLs Tab

**Press Right Arrow** again

Shows where this object is referenced:

```
Object Usage: alpha_dest1_host1

Member of Groups:
  - alpha_dest1_grp

Direct ACL References:
  - alpha_lobby_access (1 rules)

Indirect References (via groups):
  - alpha_lobby_access (via alpha_dest1_grp, 1 rules)

Total References: 2
```

**Try Export**: Press `Ctrl+E` to export usage report

---

## Tab 5: Path Check Tab

**Press Right Arrow** once more

You'll see a form:

```
Path Check - Packet Flow Simulation

Source IP/Object: alpha_dest1_host1 (pre-filled)
Destination IP/Object: [enter here]
Protocol: [tcp/udp/icmp/ip]
Destination Port: [number]

[Simulate Packet Flow]
```

### Try a Path Check:
1. Destination: `alpha_lobby_host1`
2. Protocol: `tcp`
3. Port: `80`
4. Click **Simulate Packet Flow**

Results show:
```
Path Check Result
Flow: alpha_dest1_host1 → alpha_lobby_host1 (tcp:80)

Verdict: ALLOWED / DENIED

NAT: [if NAT was applied]

ACL Evaluation:
1. [permit/deny] acl_name (interface: X direction: Y)
   access-list ...
```

**Try Export**: Press `Ctrl+E` to export path check results

---

## Navigation Quick Reference

| Key | Action |
|-----|--------|
| Type | Start searching |
| Up/Down or j/k | Navigate results |
| Enter | Select object (drill-down) |
| Left/Right | Switch tabs (in drill-down) |
| ESC | Exit drill-down / Clear search |
| Ctrl+E | **Export current tab** |
| Ctrl+T | Toggle theme |
| Ctrl+O | Open menu |
| F1 | Help |
| Ctrl+Q | Quit |

---

## Export Examples

### Details Tab → JSON
```json
{
  "name": "alpha_dest1_host1",
  "type": "object",
  "detail": "host 10.1.1.101",
  "source_file": "cisco-asa-example",
  "ip_addresses": ["10.1.1.101"],
  "count": 1,
  "member_of_groups": ["alpha_dest1_grp"],
  "exported_at": "2025-11-10T12:34:56"
}
```

### Inspect Tab → CSV
```csv
ACL,Action,Protocol,Source,Destination,Port,Raw Line
alpha_lobby_access,permit,tcp,10.0.1.0/24,10.1.1.101,80,access-list alpha_lobby_access extended permit tcp object alpha_lobby_net object alpha_dest1_host1 eq 80
```

### Compare Tab → TXT
```
Compare Results: alpha_dest1_host1 vs alpha_dest1_host2
============================================================
Rules in OLD only: 0
Rules in NEW only: 1
Common rules: 1

REMOVED RULES:
------------------------------------------------------------

ADDED RULES:
------------------------------------------------------------
  + [permit] access-list alpha_lobby_access extended permit tcp ...
```

---

## Tips for Best Results

### Good Objects to Try:
1. **alpha_dest1_host1** - Has ACL rules, group membership
2. **alpha_lobby_net** - Network object with multiple rules
3. **Web-Services** - Service object-group
4. **alpha_dest1_grp** - Object group with members

### Features to Explore:
1. **Search**: Type partial names (e.g., "alpha" shows all alpha objects)
2. **Filters**: Try protocol=tcp, port=80 in Inspect tab
3. **Compare**: Compare similar objects (host1 vs host2)
4. **Path Check**: Simulate real packet flows
5. **Export**: Save results to files for documentation

### Common Issues:

**"Used in ACLs: 0"**
- Some objects might not be referenced in ACLs
- Try objects like: alpha_dest1_host1, alpha_lobby_net

**"No matching rules"**
- Object might not be in any ACL
- Try enabling "include any" in settings (if available)
- Use Inspect tab to see why no matches

**Empty results in Path Check**
- Make sure both source and destination are valid
- Protocol must be: tcp, udp, icmp, or ip
- Port must be a number

---

## What to Export and Why

### 1. Compliance Documentation
- **Details Tab**: Document what objects exist and their IPs
- **Used in ACLs**: Prove object is/isn't being used

### 2. Change Management
- **Compare Tab**: Show before/after of firewall changes
- **Export as CSV**: Import into spreadsheets for change tickets

### 3. Troubleshooting
- **Inspect Tab**: Document all rules affecting a host
- **Path Check**: Prove why traffic is allowed/denied
- **Export as TXT**: Include in trouble tickets

### 4. Security Audits
- **Inspect Tab with Filters**: Find all permit rules for a service
- **Used in ACLs**: Find unused objects (candidates for removal)
- **Export as JSON**: Programmatic analysis

---

## Example Session

```bash
# 1. Launch TUI
./tui/__init__.py --vendor asa --config configs/cisco/cisco-asa-example

# 2. Search for "alpha_dest1"
# 3. Select "alpha_dest1_host1"
# 4. Tab through all 5 tabs to see different views
# 5. Press Ctrl+E on each tab to export
# 6. Exit with ESC, search for something else
# 7. Try "Web-Services" (a service group)
# 8. Try path check between two hosts
```

---

## Next Steps

Once you're comfortable:
1. Load your own firewall configs
2. Use filters to narrow down ACL rules
3. Export reports for documentation
4. Use path check to verify firewall behavior
5. Compare objects before/after changes
