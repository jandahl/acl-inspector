# Routing Translation Limitations

This document clearly defines what routing features ARE and ARE NOT supported in the IR translation system.

## Philosophy

The routing translation captures **essential operational config** needed to understand network topology, reachability, and basic policy. It does NOT capture advanced routing policy (route-maps, filtering, manipulation) which is complex and vendor-specific.

**Goal**: Enable engineers to understand "what networks are advertised, to whom, and how" - sufficient for migration planning and documentation.

**Non-Goal**: Translate complex routing policy that requires deep protocol knowledge and careful human review.

---

## Static Routes

### ✅ Fully Supported

| Feature | ASA | FortiGate | Notes |
|---------|-----|-----------|-------|
| Destination network | ✅ | ✅ | CIDR format in IR |
| Next-hop gateway | ✅ | ✅ | |
| Outbound interface | ✅ | ✅ | |
| Administrative distance | ✅ | ✅ | |
| Track object (reliability) | ✅ | ⚠️ | ASA only, FortiGate uses different mechanism |
| Tunneled flag (VPN routes) | ✅ | ❌ | ASA only |
| Route metric | ❌ | ❌ | Not used by static routes on either platform |

### ❌ Not Supported

- DHCP-learned routes (ASA `dhcp` keyword)
- IPv6 static routes
- VRF/routing-instance static routes
- Route tagging
- Per-route comments/descriptions

---

## OSPF

### ✅ Fully Supported

| Feature | ASA | FortiGate | Impact |
|---------|-----|-----------|--------|
| Process ID | ✅ | N/A | FortiGate has single OSPF process |
| Router ID | ✅ | ✅ | Critical for loop prevention |
| Network statements | ✅ | ✅ | Determines which interfaces run OSPF |
| Area assignment | ✅ | ✅ | Critical for topology |
| Area types (stub, NSSA) | ✅ | ✅ | Affects external route propagation |
| Area no-summary | ✅ | ✅ | Blocks inter-area routes |
| Area authentication | ✅ | ⚠️ | Type captured, keys not stored |
| Passive interfaces | ✅ | ⚠️ | Critical security feature |
| Redistribution (source, metric, subnets) | ✅ | ⚠️ | Basic redistribution only |
| Default-information originate | ✅ | ✅ | Default route advertisement |
| Administrative distance | ✅ | ✅ | Route preference |
| Auto-cost reference bandwidth | ✅ | ⚠️ | Affects metric calculation |
| Log adjacency changes | ✅ | ❌ | Logging only |

### ⚠️ Partially Supported

| Feature | Limitation | Workaround |
|---------|------------|------------|
| Authentication keys | Keys not stored (security) | Manual configuration required |
| Passive interfaces (FortiGate) | Not parsed yet | Requires interface-level config parsing |
| Redistribute route-maps | Not captured | Manual policy review required |

### ❌ Not Supported (Advanced Policy)

- **Route filtering**: distribute-list, filter-list
- **Route manipulation**: route-maps for redistribution
- **Interface-specific config**: cost, priority, hello/dead timers, network type
- **Virtual links**: Inter-area backbone connectivity
- **Summarization**: area range, summary-address
- **Maximum paths**: ECMP configuration
- **SPF throttling**: timers throttle spf
- **Graceful restart**: NSF/NSR configuration
- **BFD integration**: Fast failure detection

---

## BGP

### ✅ Fully Supported

| Feature | ASA | FortiGate | Impact |
|---------|-----|-----------|--------|
| AS number | ✅ | ✅ | Critical for peering |
| Router ID | ✅ | ✅ | BGP session identifier |
| Neighbor IP | ✅ | ✅ | Peer definition |
| Neighbor remote-as | ✅ | ✅ | eBGP vs iBGP |
| Neighbor description | ✅ | ⚠️ | Documentation |
| Neighbor password | ✅ | ⚠️ | Authentication flag only, not actual password |
| Neighbor timers (keepalive/holdtime) | ✅ | ⚠️ | Session stability |
| Network statements | ✅ | ⚠️ | Advertised networks |
| Redistribution (basic) | ✅ | ⚠️ | Source protocol only |
| Administrative distance | ✅ | ✅ | Route preference |

### ⚠️ Partially Supported

| Feature | Limitation | Workaround |
|---------|------------|------------|
| Neighbor password | Flag captured, not actual password | Manual configuration |
| FortiGate neighbor config | Limited parsing | May need manual review |

### ❌ Not Supported (Advanced Policy)

- **Route filtering**: prefix-lists, AS-path filters, distribute-lists
- **Route manipulation**: route-maps (in/out policies)
- **Community handling**: community lists, send/receive community
- **AS-path manipulation**: prepending, filtering
- **Local preference**: Influencing path selection
- **MED (metric)**: Multi-exit discriminator
- **Next-hop manipulation**: next-hop-self, next-hop-unchanged
- **Route reflectors**: client configuration, cluster-id
- **Confederations**: sub-AS configuration
- **Address families**: IPv4 unicast, multicast, VPNv4
- **Maximum paths**: ECMP for BGP
- **Soft reconfiguration**: inbound policy changes
- **Graceful restart**: BGP NSF
- **BFD integration**: Fast failure detection
- **Peer groups**: Neighbor templates
- **Update source**: Source interface for sessions
- **EBGP multihop**: TTL security

---

## EIGRP

### ✅ Fully Supported

| Feature | ASA | FortiGate | Impact |
|---------|-----|-----------|--------|
| AS number | ✅ | ❌ | FortiGate doesn't support EIGRP |
| Router ID | ✅ | ❌ | |
| Network statements | ✅ | ❌ | |
| Passive interfaces | ✅ | ❌ | |
| Redistribution (basic) | ✅ | ❌ | |

**Note**: FortiGate removed EIGRP support in FortiOS 5.x. Translation from ASA EIGRP will fail with clear error message.

### ❌ Not Supported

- **Interface bandwidth/delay**: Metric components
- **K-values**: Metric weight configuration
- **Stub configuration**: Reduce query scope
- **Authentication**: MD5 keys
- **Named EIGRP**: Modern EIGRP configuration mode
- **Summarization**: Manual summary routes
- **Variance**: Unequal-cost load balancing
- **Maximum paths**: ECMP
- **Offset lists**: Metric manipulation
- **Route filtering**: distribute-lists
- **BFD integration**

---

## RIP

### ⚠️ Minimal Support

RIP is parsed but with minimal detail capture. RIP is deprecated on most platforms.

**Reason**: RIP is legacy protocol rarely used in production. If you need RIP translation, please file an issue with your use case.

---

## Cross-Vendor Translation Notes

### ASA → FortiGate

| ASA Feature | FortiGate Equivalent | Translation Quality |
|-------------|---------------------|---------------------|
| OSPF process ID | Single OSPF process | ✅ Merged into global OSPF |
| OSPF passive-interface | Interface config | ⚠️ Requires manual interface config |
| BGP neighbor timers | Neighbor config | ✅ Direct translation |
| EIGRP | N/A | ❌ No FortiGate equivalent |
| Route tracking | Link health monitor | ⚠️ Different mechanism |

### FortiGate → ASA

| FortiGate Feature | ASA Equivalent | Translation Quality |
|-------------------|----------------|---------------------|
| OSPF (global) | OSPF process 1 | ✅ Creates process ID 1 |
| Interface-based passive | passive-interface | ⚠️ Requires interface name mapping |
| BGP AS | BGP AS | ✅ Direct translation |
| Link health monitor | Track object | ⚠️ Different mechanism |

---

## What This Means for Migration

### ✅ Safe to Translate Automatically

1. **Basic topology**: Network statements, areas, neighbors are captured
2. **Reachability**: Static routes, default routes translate reliably
3. **Basic security**: Passive interfaces (ASA), authentication flags
4. **Administrative distance**: Route preference preserved

### ⚠️ Requires Manual Review

1. **Redistribution**: Captured but may need route-map equivalent
2. **Authentication**: Passwords not stored, keys must be manually configured
3. **Timers**: Hello/dead intervals at interface level not captured
4. **Interface-specific OSPF config**: Requires additional configuration

### ❌ Requires Complete Redesign

1. **Route-maps**: Must be manually recreated (no vendor-agnostic equivalent)
2. **Prefix-lists / AS-path filters**: Must be manually recreated
3. **Complex redistribution policy**: Requires human understanding of intent
4. **Advanced BGP policy**: Community manipulation, local-pref, MED
5. **EIGRP → FortiGate**: Use OSPF or BGP instead

---

## Recommended Workflow

### For Documentation/Analysis
The current translation is **sufficient** for:
- Understanding network topology
- Documenting routing relationships
- Planning migrations
- Comparing configurations

### For Actual Migration
1. **Use translation as starting point** (70% of work done)
2. **Manual review required for**:
   - Authentication passwords/keys
   - Route filtering policy (route-maps, prefix-lists)
   - Advanced redistribution
   - Interface-specific tuning
3. **Test extensively**: Routing policy errors can cause outages
4. **Document differences**: Keep notes on manual changes

---

## Future Enhancements (Not Planned Yet)

These features are complex and low-priority unless users request them:

- Route-map translation (requires complex vendor-specific logic)
- Prefix-list translation
- Interface-level OSPF/EIGRP config (cost, timers, etc.)
- BGP peer-groups/neighbor templates
- IPv6 routing
- VRF/routing-instance support
- Multicast routing
- Policy-based routing (PBR)

---

## How to Request Features

If you need a specific routing feature for your use case:

1. File an issue at https://github.com/anthropics/claude-code/issues
2. Include:
   - Which protocol (OSPF/BGP/EIGRP)
   - Which vendor (ASA/FortiGate)
   - Example configuration snippet
   - Why it's critical for your migration

Features that affect **routing behavior** (passive interfaces, authentication, area types) are prioritized over **optimization features** (timers, metrics, tuning).

---

## Testing Your Translation

Before using translated routing config:

```bash
# 1. Translate and inspect
./aclinspector.py inspect --vendor asa --config asa.conf \
  --translate --target-vendor fortigate > fortigate-routing.conf

# 2. Check what was captured
./aclinspector.py inspect --vendor asa --config asa.conf \
  --translate --target-vendor fortigate --format json | jq '.dynamic_routing'

# 3. Compare before/after
diff -u <(grep -E "^router|^ network|^ neighbor" asa.conf) \
        <(grep -E "^config router|set router-id|edit" fortigate-routing.conf)
```

**Critical**: Always lab test routing changes before production deployment!
