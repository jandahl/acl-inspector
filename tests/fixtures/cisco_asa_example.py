ASA_EXAMPLE = """\
interface outside
 nameif outside
 security-level 0
 ip address 192.0.2.1 255.255.255.0

interface lobby
 nameif lobby
 security-level 100
 ip address 10.0.0.1 255.255.255.0

object network SRC_HOST
 host 10.0.0.10
object network DST_HOST
 host 192.0.2.10
object-group network SRC_GROUP
 network-object object SRC_HOST

access-list outside_in extended permit tcp object-group SRC_GROUP object DST_HOST eq 443
access-group outside_in in interface outside

access-list outside_out extended permit tcp object-group SRC_GROUP object DST_HOST eq 443
access-group outside_out out interface outside

access-list lobby_in extended permit tcp object-group SRC_GROUP object DST_HOST eq 443
access-group lobby_in in interface lobby

access-list lobby_out extended permit tcp object-group SRC_GROUP object DST_HOST eq 443
access-group lobby_out out interface lobby
"""
