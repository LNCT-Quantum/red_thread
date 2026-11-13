# File: backend/tests/unit/test_entities.py
import pytest
from src.case_engine.entities import classify_entity_id, EntityResolution

def test_classify_suspect():
    # Test that a valid suspect ID is recognized
    ref = classify_entity_id("suspect_001", ["suspect_001"], "victim_001")
    assert ref.resolution == EntityResolution.SUSPECT

def test_classify_victim():
    # Test that the victim ID is recognized
    ref = classify_entity_id("victim_001", ["suspect_001"], "victim_001")
    assert ref.resolution == EntityResolution.VICTIM

def test_classify_external_object():
    # Test that an external object is recognized
    ref = classify_entity_id("object_chessboard", ["suspect_001"], "victim_001")
    assert ref.resolution == EntityResolution.UNREGISTERED_EXTERNAL

def test_classify_fails_on_unknown_prefix():
    # Test that a fake ID format throws an error
    with pytest.raises(ValueError, match="unrecognised prefix"):
        classify_entity_id("fake_001", ["suspect_001"], "victim_001")