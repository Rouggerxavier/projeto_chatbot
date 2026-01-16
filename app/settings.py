import os


def _env_bool(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return str(val).strip().lower() == "true"


LLM_RENDERING_ENABLED = _env_bool("LLM_RENDERING_ENABLED", default=False)
