"""Trivial test that package imports OK"""

from spond import spond


def test_spond_import():
    """Won't get to this test if imports fail."""
    assert "spond" in globals()
