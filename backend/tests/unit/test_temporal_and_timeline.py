# File: backend/tests/unit/test_temporal_and_timeline.py
import pytest
from src.case_engine.temporal import (
    parse_timestamp, derive_ordering, TemporalCertainty, 
    TemporalFrame, OrderRelation, TemporalDescriptor
)

def test_parse_valid_timestamp():
    # Test parsing a timestamp with a valid tag
    raw = "approx. 2 years before Day 1 [approximate]"
    desc = parse_timestamp(raw)
    
    assert desc.certainty == TemporalCertainty.APPROXIMATE
    assert desc.frame == TemporalFrame.PRE_DAY_1
    assert desc.offset_before_day_1.months == 24
    assert desc.text == "approx. 2 years before Day 1"

def test_parse_fails_on_missing_tag():
    # Test that a timestamp without a tag throws an error
    with pytest.raises(ValueError, match="has no trailing certainty tag"):
        parse_timestamp("Just some time")

def test_parse_fails_on_unknown_tag():
    # Test that a made-up tag like [exact] throws an error
    with pytest.raises(ValueError, match="unrecognised certainty tag"):
        parse_timestamp("Day 1 9:00 PM [exact]") # 'exact' is not allowed

def test_derive_ordering_with_different_offsets():
    # Test that a larger offset before Day 1 means it happened earlier
    first = parse_timestamp("approx. 3 years before Day 1 [approximate]")
    second = parse_timestamp("approx. 2 years before Day 1 [approximate]")
    
    relation, basis, reason = derive_ordering(first, second)
    
    # First event (3 years) is BEFORE second event (2 years)
    assert relation == OrderRelation.BEFORE
    assert "larger offset is earlier" in reason

def test_derive_ordering_same_offsets():
    # Test that if offsets are identical, order cannot be established
    first = parse_timestamp("approx. 2 years before Day 1 [approximate]")
    second = parse_timestamp("approx. 2 years before Day 1 [approximate]")
    
    relation, basis, reason = derive_ordering(first, second)
    
    assert relation == OrderRelation.UNDETERMINED
    assert "not established" in reason

def test_derive_ordering_unanchored():
    # Test that if a time cannot be placed on the timeline, it remains undetermined
    first = parse_timestamp("Sometime in the past [unverified]")
    second = parse_timestamp("Day 1 10:00 PM [approximate]")
    
    relation, basis, reason = derive_ordering(first, second)
    
    assert relation == OrderRelation.UNDETERMINED
    assert "does not place it relative to Day 1" in reason