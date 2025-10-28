from dataclasses import dataclass, field
from typing import List, Set, Tuple, Optional, Union
import ipaddress


@dataclass
class Endpoint:
    addrs: Set[Union[ipaddress.IPv4Address, ipaddress.IPv4Network]] = field(default_factory=set)


@dataclass
class ServiceSpec:
    proto: Optional[str] = None  # 'ip'|'tcp'|'udp'|'icmp'|None
    dst_ports: List[Tuple[str, Tuple[Optional[int], Optional[int]]]] = field(default_factory=list)  # (op, (start,end))
    src_ports: List[Tuple[str, Tuple[Optional[int], Optional[int]]]] = field(default_factory=list)
    groups: Set[str] = field(default_factory=set)  # service groups referenced


@dataclass
class FlatRule:
    acl: str
    action: str  # 'permit'|'deny'
    src: Endpoint
    dst: Endpoint
    service: ServiceSpec
    raw: str


class FirewallParser:
    """Base interface for vendor-specific parsers.

    A parser must take raw config text and produce a list of FlatRule entries
    plus any metadata needed for resolution (e.g., object maps).
    """

    def __init__(self, text: str):
        self.text = text

    def flatten(self) -> List[FlatRule]:  # pragma: no cover - interface only
        raise NotImplementedError

