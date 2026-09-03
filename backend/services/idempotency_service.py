import time
from typing import Optional, Dict, Tuple, Any

# In-memory idempotency cache: (idempotency_key, application_id) -> (response_dict, created_timestamp)
_IDEMPOTENCY_CACHE: Dict[Tuple[str, str], Tuple[Dict[str, Any], float]] = {}
CACHE_TTL_SECONDS = 86400  # 24 hours retention


def get_idempotent_response(idempotency_key: Optional[str], application_id: str) -> Optional[Dict[str, Any]]:
    if not idempotency_key:
        return None
    cache_key = (idempotency_key, str(application_id))
    entry = _IDEMPOTENCY_CACHE.get(cache_key)
    if not entry:
        return None
    resp, created_at = entry
    if time.time() - created_at > CACHE_TTL_SECONDS:
        _IDEMPOTENCY_CACHE.pop(cache_key, None)
        return None
    return resp


def save_idempotent_response(idempotency_key: Optional[str], application_id: str, response_dict: Dict[str, Any]):
    if not idempotency_key:
        return
    cache_key = (idempotency_key, str(application_id))
    _IDEMPOTENCY_CACHE[cache_key] = (response_dict, time.time())
