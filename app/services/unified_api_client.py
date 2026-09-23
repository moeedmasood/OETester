"""Lazily-constructed UnifiedAPI client, shared across a single process."""
from functools import lru_cache

from ai_unified_api_client.unified_api import UnifiedAPI
from ai_unified_api_client.client import ClientCredentials


@lru_cache(maxsize=1)
def get_api(env: str, client_id: str, client_secret: str) -> UnifiedAPI:
    return UnifiedAPI(env, ClientCredentials(client_id=client_id, client_secret=client_secret))
