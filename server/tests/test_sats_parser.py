"""Tests for the SATS parser (shared._extract_sats_val)."""

import sys
sys.path.insert(0, "server")

from shared import _extract_sats_val


def test_string_value():
    """Plain strings pass through unchanged."""
    assert _extract_sats_val("hello", {}) == "hello"


def test_number_value():
    """Numbers pass through unchanged."""
    assert _extract_sats_val(42, {}) == 42


def test_bool_value():
    """Booleans pass through unchanged."""
    assert _extract_sats_val(True, {}) is True
    assert _extract_sats_val(False, {}) is False


def test_none_value():
    """None passes through unchanged."""
    assert _extract_sats_val(None, {}) is None


def test_empty_list_is_not_sats():
    """An empty list is not a SATS-encoded value, returned as-is."""
    assert _extract_sats_val([], {}) == []


def test_payloadless_enum_variant():
    """Enum variant with no payload returns the variant name."""
    atype = {
        "Sum": {
            "variants": [
                {"name": {"some": "available"}, "algebraic_type": {"Product": {"elements": []}}},
                {"name": {"some": "inProgress"}, "algebraic_type": {"Product": {"elements": []}}},
                {"name": {"some": "blocked"}, "algebraic_type": {"Product": {"elements": []}}},
                {"name": {"some": "done"}, "algebraic_type": {"Product": {"elements": []}}},
            ]
        }
    }
    assert _extract_sats_val([0, []], atype) == "available"
    assert _extract_sats_val([1, []], atype) == "inProgress"
    assert _extract_sats_val([2, []], atype) == "blocked"
    assert _extract_sats_val([3, []], atype) == "done"


def test_option_some_with_string():
    """Option<String>::Some returns the inner string."""
    atype = {
        "Sum": {
            "variants": [
                {"name": {"some": "some"}, "algebraic_type": {"String": []}},
                {"name": {"some": "none"}, "algebraic_type": {"Product": {"elements": []}}},
            ]
        }
    }
    result = _extract_sats_val([0, "hello"], atype)
    assert result == "hello", f"Expected 'hello', got {result!r}"


def test_option_none():
    """Option<T>::None returns Python None."""
    atype = {
        "Sum": {
            "variants": [
                {"name": {"some": "some"}, "algebraic_type": {"String": []}},
                {"name": {"some": "none"}, "algebraic_type": {"Product": {"elements": []}}},
            ]
        }
    }
    result = _extract_sats_val([1, []], atype)
    assert result is None, f"Expected None, got {result!r}"


def test_option_some_with_u64():
    """Option<u64>::Some returns the inner number."""
    atype = {
        "Sum": {
            "variants": [
                {"name": {"some": "some"}, "algebraic_type": {"U64": []}},
                {"name": {"some": "none"}, "algebraic_type": {"Product": {"elements": []}}},
            ]
        }
    }
    result = _extract_sats_val([0, 42], atype)
    assert result == 42, f"Expected 42, got {result!r}"


def test_enum_variant_with_single_payload():
    """Enum variant with a single data field returns {name: value}."""
    atype = {
        "Sum": {
            "variants": [
                {
                    "name": {"some": "Created"},
                    "algebraic_type": {
                        "Product": {
                            "elements": [
                                {"name": {"some": "task_id"}, "algebraic_type": {"String": []}}
                            ]
                        }
                    },
                },
                {"name": {"some": "Deleted"}, "algebraic_type": {"Product": {"elements": []}}},
            ]
        }
    }
    # Variant index 0 (Created) with payload ["task-123"]
    result = _extract_sats_val([0, ["task-123"]], atype)
    assert result == {"Created": "task-123"}, f"Expected {{'Created': 'task-123'}}, got {result!r}"


def test_enum_variant_with_multi_payload():
    """Enum variant with multiple data fields returns {name: [fields]}."""
    atype = {
        "Sum": {
            "variants": [
                {
                    "name": {"some": "Moved"},
                    "algebraic_type": {
                        "Product": {
                            "elements": [
                                {"name": {"some": "x"}, "algebraic_type": {"U64": []}},
                                {"name": {"some": "y"}, "algebraic_type": {"U64": []}},
                            ]
                        }
                    },
                },
            ]
        }
    }
    result = _extract_sats_val([0, [10, 20]], atype)
    # Product with 2 elements returns a list of field values
    assert result == {"Moved": [10, 20]}, f"Expected {{'Moved': [10, 20]}}, got {result!r}"


def test_nested_option_in_enum():
    """Enum variant containing Option<String> returns the unwrapped value."""
    atype = {
        "Sum": {
            "variants": [
                {
                    "name": {"some": "Assigned"},
                    "algebraic_type": {
                        "Product": {
                            "elements": [
                                {
                                    "name": {"some": "assignee"},
                                    "algebraic_type": {
                                        "Sum": {
                                            "variants": [
                                                {"name": {"some": "some"}, "algebraic_type": {"String": []}},
                                                {"name": {"some": "none"}, "algebraic_type": {"Product": {"elements": []}}},
                                            ]
                                        }
                                    },
                                },
                            ]
                        }
                    },
                },
            ]
        }
    }
    # Assigned { assignee: Some("bob") } → [0, [0, "bob"]]
    result = _extract_sats_val([0, [[0, "bob"]]], atype)
    # Product with 1 element returns the element directly, nested Option unwraps
    assert result == {"Assigned": "bob"}, f"Expected {{'Assigned': 'bob'}}, got {result!r}"


def test_swarm_agent_status():
    """SwarmAgentStatus enum variant (no payload) returns variant name."""
    atype = {
        "Sum": {
            "variants": [
                {"name": {"some": "online"}, "algebraic_type": {"Product": {"elements": []}}},
                {"name": {"some": "busy"}, "algebraic_type": {"Product": {"elements": []}}},
                {"name": {"some": "offline"}, "algebraic_type": {"Product": {"elements": []}}},
            ]
        }
    }
    assert _extract_sats_val([0, []], atype) == "online"
    assert _extract_sats_val([1, []], atype) == "busy"
    assert _extract_sats_val([2, []], atype) == "offline"


def test_passthrough_for_non_sats_list():
    """List that isn't 2-element SATS encoding passes through unchanged."""
    assert _extract_sats_val([1, 2, 3], {}) == [1, 2, 3]
    assert _extract_sats_val(["a"], {}) == ["a"]


def test_builtin_type_passthrough():
    """Builtin type with no Sum/Product passes through via fallback."""
    atype = {"String": []}
    # Even though this is a 2-element list, it's not recognized as a Sum type
    # So it falls through to the fallback
    result = _extract_sats_val([0, "hello"], atype)
    # Fallback: val[0] == 0 → val[1] = "hello" → truthy → returns "hello"
    assert result == "hello"
