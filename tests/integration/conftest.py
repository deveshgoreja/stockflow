import pytest


@pytest.fixture(autouse=True)
def _start_from_empty_database(clean_database: None) -> None:
    """Every integration test starts from empty tables."""
