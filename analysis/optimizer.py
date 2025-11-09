"""Policy optimization analyzer for firewall configurations.

Analyzes ACL policies to identify:
- Redundant rules (exact duplicates)
- Shadowed rules (never match due to earlier rules)
- Overly permissive rules (any/any permits)
- Unused object references
- Optimization opportunities (rule consolidation)
"""

from __future__ import annotations

from typing import List, Dict, Set, Tuple, Any, Optional
from dataclasses import dataclass
from collections import defaultdict


@dataclass
class OptimizationIssue:
    """Represents an optimization opportunity or policy issue."""
    severity: str  # 'critical', 'warning', 'info'
    category: str  # 'redundant', 'shadowed', 'permissive', 'unused', 'consolidation'
    rule_index: int
    rule_text: str
    message: str
    suggestion: Optional[str] = None
    related_rules: List[int] = None  # Indices of related rules

    def __post_init__(self):
        if self.related_rules is None:
            self.related_rules = []


class PolicyOptimizer:
    """Analyzes and optimizes firewall ACL policies."""

    def __init__(self, acls: List[Dict[str, Any]]):
        """Initialize optimizer with ACL data.

        Args:
            acls: List of ACL entries from IR format
        """
        self.acls = acls
        self.issues: List[OptimizationIssue] = []

    def analyze(self) -> List[OptimizationIssue]:
        """Run all optimization analyses.

        Returns:
            List of optimization issues found
        """
        self.issues = []

        self._find_exact_duplicates()
        self._find_shadowed_rules()
        self._find_overly_permissive()
        self._find_consolidation_opportunities()

        # Sort by severity
        severity_order = {'critical': 0, 'warning': 1, 'info': 2}
        self.issues.sort(key=lambda i: (severity_order.get(i.severity, 3), i.rule_index))

        return self.issues

    def _find_exact_duplicates(self) -> None:
        """Find rules that are exact duplicates."""
        seen: Dict[Tuple, List[int]] = defaultdict(list)

        for idx, acl in enumerate(self.acls):
            # Create normalized tuple for comparison
            key = self._normalize_rule(acl)
            seen[key].append(idx)

        # Report duplicates
        for key, indices in seen.items():
            if len(indices) > 1:
                for idx in indices[1:]:  # Skip first occurrence
                    self.issues.append(OptimizationIssue(
                        severity='warning',
                        category='redundant',
                        rule_index=idx,
                        rule_text=self.acls[idx].get('raw', str(self.acls[idx])),
                        message=f'Exact duplicate of rule at index {indices[0]}',
                        suggestion=f'Remove this rule (duplicate of #{indices[0]})',
                        related_rules=[indices[0]]
                    ))

    def _find_shadowed_rules(self) -> None:
        """Find rules that will never match due to earlier rules."""
        for idx, rule in enumerate(self.acls):
            # Check if this rule is shadowed by any earlier rule
            for earlier_idx in range(idx):
                earlier = self.acls[earlier_idx]

                # Skip if different actions
                if rule.get('action') != earlier.get('action'):
                    continue

                # Check if earlier rule is more general
                if self._rule_shadows(earlier, rule):
                    self.issues.append(OptimizationIssue(
                        severity='critical',
                        category='shadowed',
                        rule_index=idx,
                        rule_text=rule.get('raw', str(rule)),
                        message=f'Shadowed by earlier rule at index {earlier_idx} - will never match',
                        suggestion=f'Move before rule #{earlier_idx} or remove if truly redundant',
                        related_rules=[earlier_idx]
                    ))
                    break  # One shadow is enough to report

    def _find_overly_permissive(self) -> None:
        """Find rules that are overly permissive (e.g., permit any any)."""
        for idx, rule in enumerate(self.acls):
            if rule.get('action') != 'permit':
                continue

            src = rule.get('src', [])
            dst = rule.get('dst', [])
            proto = rule.get('proto')

            # Check for any-any permits
            if self._is_any(src) and self._is_any(dst) and (not proto or proto == 'ip'):
                self.issues.append(OptimizationIssue(
                    severity='critical',
                    category='permissive',
                    rule_index=idx,
                    rule_text=rule.get('raw', str(rule)),
                    message='Overly permissive: permits all traffic from any to any',
                    suggestion='Restrict source, destination, or protocol'
                ))
            # Check for any source with specific destination
            elif self._is_any(src) and not self._is_any(dst):
                self.issues.append(OptimizationIssue(
                    severity='warning',
                    category='permissive',
                    rule_index=idx,
                    rule_text=rule.get('raw', str(rule)),
                    message='Permits traffic from any source (consider restricting)',
                    suggestion='Limit source addresses to known networks'
                ))

    def _find_consolidation_opportunities(self) -> None:
        """Find rules that could potentially be consolidated."""
        # Group rules by action and protocol
        groups: Dict[Tuple, List[int]] = defaultdict(list)

        for idx, rule in enumerate(self.acls):
            key = (rule.get('action'), rule.get('proto'))
            groups[key].append(idx)

        # Look for consolidation opportunities within groups
        for (action, proto), indices in groups.items():
            if len(indices) < 2:
                continue

            # Check for rules with same src/dst that differ only in service
            consolidatable = self._find_service_consolidation(indices)
            if consolidatable:
                for group in consolidatable:
                    if len(group) >= 3:  # Worth consolidating if 3+ rules
                        first_idx = group[0]
                        self.issues.append(OptimizationIssue(
                            severity='info',
                            category='consolidation',
                            rule_index=first_idx,
                            rule_text=self.acls[first_idx].get('raw', ''),
                            message=f'Could consolidate {len(group)} similar rules into a service group',
                            suggestion='Create a service object-group combining these ports',
                            related_rules=group[1:]
                        ))

    def _normalize_rule(self, rule: Dict[str, Any]) -> Tuple:
        """Normalize rule to tuple for comparison."""
        return (
            rule.get('action'),
            rule.get('proto'),
            tuple(sorted(rule.get('src', []))),
            tuple(sorted(rule.get('dst', []))),
            str(rule.get('svc', {}))  # Simple string comparison for service
        )

    def _rule_shadows(self, general: Dict[str, Any], specific: Dict[str, Any]) -> bool:
        """Check if general rule shadows (makes unreachable) specific rule.

        A rule shadows another if:
        - Same action
        - General's source contains specific's source
        - General's destination contains specific's destination
        - General's protocol/service matches or is broader
        """
        # Already checked: same action

        # Check source containment
        gen_src = set(general.get('src', []))
        spec_src = set(specific.get('src', []))
        if not (self._is_any(gen_src) or spec_src.issubset(gen_src)):
            return False

        # Check destination containment
        gen_dst = set(general.get('dst', []))
        spec_dst = set(specific.get('dst', []))
        if not (self._is_any(gen_dst) or spec_dst.issubset(gen_dst)):
            return False

        # Check protocol/service
        gen_proto = general.get('proto')
        spec_proto = specific.get('proto')

        if gen_proto == 'ip' or not gen_proto:
            return True  # 'ip' or unspecified matches all protocols

        if gen_proto != spec_proto:
            return False

        # For now, simplified service comparison
        # TODO: Detailed port range containment check
        return True

    def _is_any(self, addresses: Any) -> bool:
        """Check if address list represents 'any'."""
        if not addresses:
            return True
        if isinstance(addresses, (list, set)):
            return 'any' in addresses or 'any4' in addresses or len(addresses) == 0
        return addresses in ('any', 'any4')

    def _find_service_consolidation(self, indices: List[int]) -> List[List[int]]:
        """Find groups of rules that differ only in service/port."""
        groups: Dict[Tuple, List[int]] = defaultdict(list)

        for idx in indices:
            rule = self.acls[idx]
            # Group by src/dst (ignoring service)
            key = (
                tuple(sorted(rule.get('src', []))),
                tuple(sorted(rule.get('dst', [])))
            )
            groups[key].append(idx)

        # Return groups with multiple rules
        return [g for g in groups.values() if len(g) > 1]

    def generate_report(self, format: str = 'text') -> str:
        """Generate optimization report.

        Args:
            format: Output format ('text', 'json', 'markdown')

        Returns:
            Formatted report string
        """
        if format == 'text':
            return self._generate_text_report()
        elif format == 'json':
            import json
            return json.dumps([
                {
                    'severity': i.severity,
                    'category': i.category,
                    'rule_index': i.rule_index,
                    'message': i.message,
                    'suggestion': i.suggestion,
                    'related_rules': i.related_rules
                }
                for i in self.issues
            ], indent=2)
        elif format == 'markdown':
            return self._generate_markdown_report()
        else:
            raise ValueError(f"Unknown format: {format}")

    def _generate_text_report(self) -> str:
        """Generate plain text report."""
        lines = ["Policy Optimization Report", "=" * 50, ""]

        if not self.issues:
            lines.append("No optimization issues found. Policy looks good!")
            return "\n".join(lines)

        # Group by severity
        by_severity = defaultdict(list)
        for issue in self.issues:
            by_severity[issue.severity].append(issue)

        for severity in ['critical', 'warning', 'info']:
            issues = by_severity.get(severity, [])
            if not issues:
                continue

            lines.append(f"\n{severity.upper()} Issues ({len(issues)}):")
            lines.append("-" * 50)

            for issue in issues:
                lines.append(f"\nRule #{issue.rule_index}: {issue.category}")
                lines.append(f"  {issue.message}")
                if issue.suggestion:
                    lines.append(f"  Suggestion: {issue.suggestion}")
                if issue.related_rules:
                    lines.append(f"  Related rules: {', '.join(f'#{r}' for r in issue.related_rules)}")

        lines.append(f"\n\nTotal issues: {len(self.issues)}")
        lines.append(f"  Critical: {len(by_severity['critical'])}")
        lines.append(f"  Warnings: {len(by_severity['warning'])}")
        lines.append(f"  Info: {len(by_severity['info'])}")

        return "\n".join(lines)

    def _generate_markdown_report(self) -> str:
        """Generate markdown report."""
        lines = ["# Policy Optimization Report\n"]

        if not self.issues:
            lines.append("**No optimization issues found.** Policy looks good!\n")
            return "\n".join(lines)

        # Summary
        by_severity = defaultdict(list)
        for issue in self.issues:
            by_severity[issue.severity].append(issue)

        lines.append("## Summary\n")
        lines.append(f"- **Critical:** {len(by_severity['critical'])}")
        lines.append(f"- **Warnings:** {len(by_severity['warning'])}")
        lines.append(f"- **Info:** {len(by_severity['info'])}")
        lines.append(f"- **Total:** {len(self.issues)}\n")

        # Details by severity
        for severity in ['critical', 'warning', 'info']:
            issues = by_severity.get(severity, [])
            if not issues:
                continue

            emoji = {'critical': '🔴', 'warning': '🟡', 'info': '🔵'}
            lines.append(f"## {emoji[severity]} {severity.capitalize()} Issues\n")

            for issue in issues:
                lines.append(f"### Rule #{issue.rule_index}: {issue.category}\n")
                lines.append(f"**Message:** {issue.message}\n")
                if issue.suggestion:
                    lines.append(f"**Suggestion:** {issue.suggestion}\n")
                if issue.related_rules:
                    lines.append(f"**Related rules:** {', '.join(f'#{r}' for r in issue.related_rules)}\n")

        return "\n".join(lines)


def optimize_policy(acls: List[Dict[str, Any]], format: str = 'text') -> str:
    """Convenience function to analyze and generate optimization report.

    Args:
        acls: List of ACL entries from IR format
        format: Output format ('text', 'json', 'markdown')

    Returns:
        Formatted optimization report
    """
    optimizer = PolicyOptimizer(acls)
    optimizer.analyze()
    return optimizer.generate_report(format=format)
