"""Network and IP address utilities for ASA parser.

Utility functions for working with IPv4 addresses and networks.
"""

from __future__ import annotations

import ipaddress
from typing import Optional, Set, Union

__all__ = ["to_ip_network", "nets_overlap"]


def to_ip_network(ip: str, mask: Optional[str] = None) -> Union[ipaddress.IPv4Address, ipaddress.IPv4Network]:
    """Parse IP address or network from ASA config format.

    Args:
        ip: IP address string
        mask: Optional netmask string (for network)

    Returns:
        IPv4Address if single host, IPv4Network if network with mask
    """
    if mask is not None:
        return ipaddress.IPv4Network(f"{ip}/{mask}", strict=False)
    if "/" in ip:
        return ipaddress.IPv4Network(ip, strict=False)
    return ipaddress.ip_address(ip)


def nets_overlap(
    set_a: Set[Union[ipaddress.IPv4Address, ipaddress.IPv4Network]],
    set_b: Set[Union[ipaddress.IPv4Address, ipaddress.IPv4Network]]
) -> bool:
    """Check if two sets of networks/addresses overlap.

    Args:
        set_a: First set of addresses/networks
        set_b: Second set of addresses/networks

    Returns:
        True if any address/network in set_a overlaps with any in set_b
    """
    for net_a in set_a:
        if not isinstance(net_a, (ipaddress.IPv4Address, ipaddress.IPv4Network)):
            continue
        for net_b in set_b:
            if not isinstance(net_b, (ipaddress.IPv4Address, ipaddress.IPv4Network)):
                continue
            if isinstance(net_a, ipaddress.IPv4Address) and isinstance(net_b, ipaddress.IPv4Address):
                if net_a == net_b:
                    return True
            elif isinstance(net_a, ipaddress.IPv4Network) and isinstance(net_b, ipaddress.IPv4Address):
                if net_b in net_a:
                    return True
            elif isinstance(net_a, ipaddress.IPv4Address) and isinstance(net_b, ipaddress.IPv4Network):
                if net_a in net_b:
                    return True
            elif isinstance(net_a, ipaddress.IPv4Network) and isinstance(net_b, ipaddress.IPv4Network):
                if net_a.overlaps(net_b):
                    return True
    return False
