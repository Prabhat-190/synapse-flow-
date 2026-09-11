import pytest


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    from atlas.gateway.security import _rate_buckets

    _rate_buckets.clear()
    yield
    _rate_buckets.clear()
