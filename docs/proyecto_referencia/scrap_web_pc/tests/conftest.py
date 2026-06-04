import pytest

def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "integration: live network tests — skip in unit runs with -m 'not integration'",
    )
