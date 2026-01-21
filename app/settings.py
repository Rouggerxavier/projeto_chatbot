import os


def _env_bool(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return str(val).strip().lower() == "true"

# Simple float loader with bounds and default
def _env_float(name: str, default: float, min_val: float = 0.0, max_val: float = 1.0) -> float:
    try:
        val = float(os.getenv(name, str(default)))
    except Exception:
        return default
    return max(min_val, min(max_val, val))

LLM_RENDERING_ENABLED = _env_bool("LLM_RENDERING_ENABLED", default=False)

# Confidence thresholds for LLM decisions (defaults chosen to block low-confidence actions)
ROUTER_CONFIDENCE_THRESHOLD = _env_float("ROUTER_CONFIDENCE_THRESHOLD", default=0.65)
PLANNER_CONFIDENCE_THRESHOLD = _env_float("PLANNER_CONFIDENCE_THRESHOLD", default=0.70)
# Hard block: always clarify below this level
LLM_HARD_BLOCK_THRESHOLD = _env_float("LLM_HARD_BLOCK_THRESHOLD", default=0.40)
