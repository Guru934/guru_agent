# Holds organizational policies and guidelines for agent execution.
# e.g., safe mode evaluation, execution limits, etc.

def evaluate_safety(action_type: str, safe_mode: bool) -> bool:
    """Returns True if the action is allowed under the current policy."""
    if safe_mode and action_type in ["bash", "write"]:
        return False
    return True
