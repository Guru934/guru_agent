
import os
import uuid
import datetime
from pathlib import Path
from dataclasses import dataclass
from agent.tool_registry import registry
from config import WORKSPACE_ROOTS, USER_STATE_DIR
from agent.events import emit

@dataclass
class PolicyDecision:
    allowed: bool
    requires_approval: bool
    risk_level: str
    reason: str

class PolicyEngine:
    def __init__(self, safe_mode: bool = True):
        self.safe_mode = safe_mode
        self.blocked_commands = [
            "rm -rf /", "mkfs", "dd if=", "shutdown", "reboot", 
            "passwd", "chown -R", "chmod -R 777", "curl | bash",
            "wget -qO-", "nc -e", "> /dev/sda"
        ]
        
        self.safe_commands = [
            "ls", "pwd", "whoami", "echo", "cat", "git status", 
            "git diff", "git log", "pytest", "python -m unittest"
        ]
        self.audit_file = USER_STATE_DIR / "security_audit.log"
        
    def _log_audit(self, tool_name: str, arguments: dict, target_risk: str, decision: PolicyDecision):
        """Append to strict security audit log outside the project root."""
        try:
            timestamp = datetime.datetime.now().isoformat()
            log_line = f"[{timestamp}] TOOL={tool_name} RISK={target_risk} ALLOWED={decision.allowed} APPROVAL={decision.requires_approval} REASON='{decision.reason}' ARGS={arguments}\n"
            with open(self.audit_file, "a") as f:
                f.write(log_line)
        except Exception:
            pass

    def _is_path_allowed(self, path_str: str) -> bool:
        """Check if a path falls within the allowed workspace roots."""
        try:
            target = Path(os.path.expanduser(path_str)).resolve()
            for root in WORKSPACE_ROOTS:
                if target == root or target.is_relative_to(root):
                    return True
            return False
        except Exception:
            return False

    def evaluate(self, tool_name: str, arguments: dict, context: dict) -> PolicyDecision:
        spec = registry.get_spec(tool_name)
        if not spec:
            dec = PolicyDecision(False, False, "unknown", f"Tool {tool_name} is not registered.")
            self._log_audit(tool_name, arguments, "unknown", dec)
            return dec
            
        risk = spec.risk
        decision = None
        
        if tool_name == "execute_shell":
            cmd = arguments.get("command", "")
            
            # 1. Check BLOCKED commands
            if any(blk in cmd for blk in self.blocked_commands):
                decision = PolicyDecision(False, False, "critical", "Command matches a heavily restricted BLOCKED signature.")
            else:
                # 2. Check SAFE commands
                cmd_basename = cmd.strip().split()[0] if cmd.strip() else ""
                is_implicitly_safe = any(cmd.strip().startswith(safe_cmd) for safe_cmd in self.safe_commands)
                
                if is_implicitly_safe:
                    decision = PolicyDecision(True, False, "low", "Known read-only or harmless diagnostic command.")
                # 3. Handling modifications and unknown commands (APPROVAL tier)
                elif self.safe_mode:
                    decision = PolicyDecision(True, True, risk, "Safe mode requires manual approval for potentially mutable shell execution.")
                else:
                    decision = PolicyDecision(True, False, risk, "Shell execution allowed without safe mode.")
            
        elif tool_name in ["write_file", "read_file", "search"]:
            path = arguments.get("path", "") or arguments.get("query", "") # if search query acts on a path
            if getattr(spec, "name") in ["write_file", "read_file"] and not self._is_path_allowed(path):
                decision = PolicyDecision(False, False, "critical", f"Path '{path}' is OUTSIDE the allowed workspace roots.")
            elif risk == "high" or risk == "medium":
                if self.safe_mode:
                    decision = PolicyDecision(True, True, risk, f"Safe mode requires manual approval for {risk}-risk actions.")
                else:
                    decision = PolicyDecision(True, False, risk, f"{risk.capitalize()}-risk action allowed.")
            else:
                decision = PolicyDecision(True, False, risk, "Low-risk action allowed automatically.")
                
        else:
            # Fallback wrapper
            decision = PolicyDecision(True, False, risk, "Fallback generic low-risk rule.")

        # Log and return
        if decision:
            self._log_audit(tool_name, arguments, risk, decision)
            return decision

        return PolicyDecision(False, False, "error", "Policy engine fell through to default block rule.")

engine = PolicyEngine(safe_mode=True)
