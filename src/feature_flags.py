"""Feature flags — controls for toggling reminder automation.

In production, this uses Unleash (self-hosted) for flag evaluation.
For testing / local dev, the REMINDERS_ENABLED env var can override the flag.

Design:
  - Default is True (reminders enabled) — safe default for production.
  - The Unleash client is optional; if not configured, the flag falls back
    to the REMINDERS_ENABLED env var, then to True.
"""
import os
import logging

_unleash_client = None


def _get_unleash_client():
    """Lazy-init the Unleash client. Returns None if not configured."""
    global _unleash_client
    if _unleash_client is not None:
        return _unleash_client

    unleash_url = os.getenv('UNLEASH_URL')
    if not unleash_url:
        return None

    try:
        from UnleashClient import UnleashClient
        _unleash_client = UnleashClient(
            url=unleash_url,
            app_name='yourinboxhero',
            instance_id='default',
        )
        _unleash_client.initialize_client()
        return _unleash_client
    except Exception as exc:
        logging.warning(f'Failed to initialize Unleash client: {exc}')
        return None


def reminders_enabled() -> bool:
    """Check whether automated reminders are enabled.

    Resolution order:
      1. REMINDERS_ENABLED env var (explicit override for tests/local dev)
      2. Unleash flag 'reminders-enabled'
      3. Default: True
    """
    # Env var override (useful for tests and local dev)
    env_override = os.getenv('REMINDERS_ENABLED')
    if env_override is not None:
        return env_override.lower() in ('true', '1', 'yes')

    # Try Unleash
    client = _get_unleash_client()
    if client is not None:
        try:
            return client.is_enabled('reminders-enabled', default_value=True)
        except Exception as exc:
            logging.warning(f'Unleash flag check failed: {exc}')

    # Default: enabled
    return True
