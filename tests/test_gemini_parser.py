"""
Tests for Gemini response parser.
The parser is the safety boundary — these tests are critical.
"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.external.gemini.parser import parse_gemini_response


class TestValidResponses:
    
    def test_clean_table_with_objects(self):
        raw = '{"proposal_type": "CLEAN_TABLE", "object_ids": [5, 8, 12], "rationale": "messy"}'
        result = parse_gemini_response(raw)
        
        assert result.success
        assert result.proposal.action.value == "clean_table"
        assert result.proposal.source == "gemini"
        assert result.proposal.suggested_object_ids == [5, 8, 12]
    
    def test_clean_table_without_objects(self):
        raw = '{"proposal_type": "CLEAN_TABLE", "rationale": "table is messy"}'
        result = parse_gemini_response(raw)
        
        assert result.success
        assert result.proposal.action.value == "clean_table"
        assert result.proposal.suggested_object_ids is None
    
    def test_none_proposal(self):
        raw = '{"proposal_type": "NONE", "rationale": "table is clean"}'
        result = parse_gemini_response(raw)
        
        assert result.success
        assert result.proposal.action.value == "idle"
        assert result.proposal.source == "gemini"
    
    def test_strips_markdown_fences(self):
        raw = '```json\n{"proposal_type": "CLEAN_TABLE", "object_ids": [1]}\n```'
        result = parse_gemini_response(raw)
        
        assert result.success
        assert result.proposal.action.value == "clean_table"


class TestInvalidResponses:
    
    def test_empty_string(self):
        result = parse_gemini_response("")
        assert result.rejected
        assert "length" in result.reason
    
    def test_not_json(self):
        result = parse_gemini_response("This is not JSON at all.")
        assert result.rejected
        assert "json_decode" in result.reason
    
    def test_json_array_not_object(self):
        result = parse_gemini_response('[1, 2, 3]')
        assert result.rejected
        assert "not_object" in result.reason
    
    def test_invalid_proposal_type(self):
        raw = '{"proposal_type": "DESTROY_WORLD", "object_ids": [1]}'
        result = parse_gemini_response(raw)
        assert result.rejected
        assert "invalid_proposal_type" in result.reason
    
    def test_missing_proposal_type(self):
        raw = '{"object_ids": [1, 2]}'
        result = parse_gemini_response(raw)
        assert result.rejected
        assert "invalid_proposal_type" in result.reason
    
    def test_object_ids_not_list(self):
        raw = '{"proposal_type": "CLEAN_TABLE", "object_ids": "not a list"}'
        result = parse_gemini_response(raw)
        assert result.rejected
        assert "object_ids_not_list" in result.reason
    
    def test_extremely_long_response(self):
        raw = '{"proposal_type": "CLEAN_TABLE"}' + ' ' * 20000
        result = parse_gemini_response(raw)
        assert result.rejected
        assert "length" in result.reason


class TestObjectIdValidation:
    
    def test_filters_invalid_object_ids(self):
        raw = '{"proposal_type": "CLEAN_TABLE", "object_ids": [5, 99, 8]}'
        valid_ids = {5, 8, 10}
        
        result = parse_gemini_response(raw, valid_ids)
        
        assert result.success
        assert 99 not in result.proposal.suggested_object_ids
        assert result.proposal.suggested_object_ids == [5, 8]
    
    def test_all_ids_invalid_returns_none_ids(self):
        raw = '{"proposal_type": "CLEAN_TABLE", "object_ids": [99, 100]}'
        valid_ids = {5, 8}
        
        result = parse_gemini_response(raw, valid_ids)
        
        assert result.success  # Still valid proposal
        assert result.proposal.suggested_object_ids is None  # All filtered
    
    def test_deduplicates_object_ids(self):
        raw = '{"proposal_type": "CLEAN_TABLE", "object_ids": [5, 5, 8, 8]}'
        result = parse_gemini_response(raw)
        
        assert result.success
        assert result.proposal.suggested_object_ids == [5, 8]


class TestEdgeCases:
    
    def test_unknown_keys_ignored(self):
        raw = '{"proposal_type": "CLEAN_TABLE", "object_ids": [1], "unknown_field": "whatever"}'
        result = parse_gemini_response(raw)
        assert result.success  # Unknown keys logged but not rejected
    
    def test_null_object_ids(self):
        raw = '{"proposal_type": "CLEAN_TABLE", "object_ids": null}'
        result = parse_gemini_response(raw)
        # null is handled gracefully - treated as missing, so no object_ids
        assert result.success
        assert result.proposal.suggested_object_ids is None
    
    def test_float_object_ids_converted(self):
        raw = '{"proposal_type": "CLEAN_TABLE", "object_ids": [5.0, 8.0]}'
        result = parse_gemini_response(raw)
        
        assert result.success
        assert result.proposal.suggested_object_ids == [5, 8]
    
    def test_none_input_handled_safely(self):
        """Parser should never raise exceptions"""
        result = parse_gemini_response(None)  # type: ignore
        assert result.rejected
        # Should not raise exception


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
