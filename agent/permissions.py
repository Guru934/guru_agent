from dataclasses import dataclass
from typing import Optional

from agent.policy import PolicyDecision
from agent.capabilities import registry as capability_registry


@dataclass
class PermissionDecision:
    allowed: bool
    requires_approval: bool
    risk_level: str
    reason: str
    source: str = "policy_default"

    @staticmethod
    def from_policy(policy_decision: PolicyDecision, source: str = "policy_default") -> "PermissionDecision":
        return PermissionDecision(
            allowed=policy_decision.allowed,
            requires_approval=policy_decision.requires_approval,
            risk_level=policy_decision.risk_level,
            reason=policy_decision.reason,
            source=source,
        )

    def with_grant(self, grant_id: str) -> "PermissionDecision":
        return PermissionDecision(
            allowed=self.allowed,
            requires_approval=False,
            risk_level=self.risk_level,
            reason=f"Allowed by capability grant {grant_id}",
            source="user_grant",
        )

    def blocked(self, reason: str) -> "PermissionDecision":
        return PermissionDecision(
            allowed=False,
            requires_approval=False,
            risk_level="critical",
            reason=reason,
            source="blocked",
        )


def check_capability_grant(tool_name: str, arguments: dict) -> Optional[str]:
    grant = capability_registry.check_grant(tool_name, arguments)
    if grant:
        return grant.id
    return None


def apply_capability_grant(decision: PolicyDecision, grant_id: Optional[str]) -> PermissionDecision:
    perm = PermissionDecision.from_policy(decision)
    if grant_id:
        return perm.with_grant(grant_id)
    return perm