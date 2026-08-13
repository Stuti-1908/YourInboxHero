import importlib

def test_schedule_reminders_module_exists():
    """The Azure Function entry point module must exist and expose a `main` function."""
    mod = importlib.import_module('src.functions.schedule_reminders')
    assert hasattr(mod, 'main'), "schedule_reminders module must expose a main() function"
    assert callable(mod.main), "main must be callable"