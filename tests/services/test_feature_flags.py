"""Tests for feature_flags — reminders_enabled()."""
import os


def test_reminders_enabled_default_true():
    """Without any env var or Unleash, reminders should default to enabled."""
    # Ensure no override env var is set
    env_backup = os.environ.pop('REMINDERS_ENABLED', None)
    unleash_backup = os.environ.pop('UNLEASH_URL', None)
    try:
        # Reset the module-level cached client
        import src.feature_flags as ff
        ff._unleash_client = None
        assert ff.reminders_enabled() is True
    finally:
        if env_backup is not None:
            os.environ['REMINDERS_ENABLED'] = env_backup
        if unleash_backup is not None:
            os.environ['UNLEASH_URL'] = unleash_backup


def test_reminders_disabled_via_env_var(monkeypatch):
    """Setting REMINDERS_ENABLED=false should disable reminders."""
    monkeypatch.setenv('REMINDERS_ENABLED', 'false')
    from src.feature_flags import reminders_enabled
    assert reminders_enabled() is False


def test_reminders_enabled_via_env_var(monkeypatch):
    """Setting REMINDERS_ENABLED=true should enable reminders."""
    monkeypatch.setenv('REMINDERS_ENABLED', 'true')
    from src.feature_flags import reminders_enabled
    assert reminders_enabled() is True


def test_reminders_enabled_env_var_case_insensitive(monkeypatch):
    """Env var should be case-insensitive: 'True', 'TRUE', 'yes', '1' all enable."""
    from src.feature_flags import reminders_enabled
    for val in ('True', 'TRUE', 'yes', '1'):
        monkeypatch.setenv('REMINDERS_ENABLED', val)
        assert reminders_enabled() is True, f'Expected True for REMINDERS_ENABLED={val}'


def test_process_due_reminders_skips_when_flag_disabled(monkeypatch):
    """process_due_reminders should return early when feature flag is off."""
    monkeypatch.setenv('REMINDERS_ENABLED', 'false')
    from unittest.mock import patch
    with patch('src.services.reminder_service.get_eligible_invoices') as mock_query:
        from src.services.reminder_service import process_due_reminders
        process_due_reminders()
        # get_eligible_invoices should NOT have been called
        mock_query.assert_not_called()
