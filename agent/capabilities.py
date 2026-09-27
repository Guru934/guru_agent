import json
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from config import USER_STATE_DIR
from memory.sqlite import get_db_connection


@dataclass
class CapabilityGrant:
    id: str
    capability: str
    constraints: Dict[str, Any]
    scope: str
    enabled: bool
    created_at: str
    expires_at: Optional[str] = None

    @staticmethod
    def from_row(row: tuple) -> "CapabilityGrant":
        return CapabilityGrant(
            id=row[0],
            capability=row[1],
            constraints=json.loads(row[2]) if row[2] else {},
            scope=row[3],
            enabled=bool(row[4]),
            created_at=row[5],
            expires_at=row[6],
        )

    def to_row(self) -> tuple:
        return (
            self.id,
            self.capability,
            json.dumps(self.constraints),
            self.scope,
            int(self.enabled),
            self.created_at,
            self.expires_at,
        )

    def matches(self, capability: str, arguments: Dict[str, Any]) -> bool:
        if not self.enabled:
            return False
        if self.capability != capability:
            return False
        if self.expires_at:
            try:
                if datetime.fromisoformat(self.expires_at) < datetime.now():
                    return False
            except ValueError:
                pass
        return self._constraints_match(arguments)

    def _constraints_match(self, arguments: Dict[str, Any]) -> bool:
        for key, expected in self.constraints.items():
            if key not in arguments:
                return False
            actual = arguments[key]
            if isinstance(expected, list):
                if actual not in expected:
                    return False
            elif isinstance(expected, dict):
                if "min" in expected and actual < expected["min"]:
                    return False
                if "max" in expected and actual > expected["max"]:
                    return False
            elif actual != expected:
                return False
        return True


class CapabilityRegistry:
    def __init__(self):
        self._grants: Dict[str, CapabilityGrant] = {}
        self._lock = threading.RLock()
        self._load_grants()

    def _load_grants(self):
        with get_db_connection() as conn:
            cursor = conn.execute("SELECT * FROM capability_grants WHERE enabled = 1")
            for row in cursor.fetchall():
                grant = CapabilityGrant.from_row(row)
                self._grants[grant.id] = grant

    def register_grant(self, grant: CapabilityGrant) -> None:
        with self._lock:
            self._grants[grant.id] = grant
            self._persist_grant(grant)

    def _persist_grant(self, grant: CapabilityGrant) -> None:
        with get_db_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO capability_grants
                (id, capability, constraints_json, scope, enabled, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                grant.to_row(),
            )
            conn.commit()

    def revoke_grant(self, grant_id: str) -> bool:
        with self._lock:
            if grant_id not in self._grants:
                return False
            grant = self._grants[grant_id]
            grant.enabled = False
            self._persist_grant(grant)
            del self._grants[grant_id]
            return True

    def get_grant(self, grant_id: str) -> Optional[CapabilityGrant]:
        with self._lock:
            return self._grants.get(grant_id)

    def get_all_grants(self) -> List[CapabilityGrant]:
        with self._lock:
            return list(self._grants.values())

    def check_grant(self, capability: str, arguments: Dict[str, Any]) -> Optional[CapabilityGrant]:
        with self._lock:
            for grant in self._grants.values():
                if grant.matches(capability, arguments):
                    return grant
            return None

    def get_grants_for_capability(self, capability: str) -> List[CapabilityGrant]:
        with self._lock:
            return [g for g in self._grants.values() if g.capability == capability and g.enabled]


registry = CapabilityRegistry()