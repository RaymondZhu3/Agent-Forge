import pytest


@pytest.fixture(autouse=True)
def _fresh_model_cooldowns():
    """Model cooldowns are process-wide (they span runs on purpose); tests must not leak them."""
    from server.runtime import llm

    llm._cooldown_until.clear()
    yield
    llm._cooldown_until.clear()
