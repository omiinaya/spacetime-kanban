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
    # Assigned { assignee: Some("bob") } → [0, [[0, "bob"]]]
    result = _extract_sats_val([0, [[0, "bob"]]], atype)
    # Product with 1 element returns the element directly, nested Option unwraps
    assert result == {"Assigned": "bob"}, f"Expected {{'Assigned': 'bob'}}, got {result!r}"


def test_nested_option_some_none():
    """Nested Option<Option<String>>::Some(None) returns None."""
    inner_opt = {
        "Sum": {
            "variants": [
                {"name": {"some": "some"}, "algebraic_type": {"String": []}},
                {"name": {"some": "none"}, "algebraic_type": {"Product": {"elements": []}}},
            ]
        }
    }
    outer_opt = {
        "Sum": {
            "variants": [
                {"name": {"some": "some"}, "algebraic_type": inner_opt},
                {"name": {"some": "none"}, "algebraic_type": {"Product": {"elements": []}}},
            ]
        }
    }
    # Some(None) → [0, [1, []]]
    result = _extract_sats_val([0, [1, []]], outer_opt)
    assert result is None, f"Expected None, got {result!r}"


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
    """Builtin type with no Sum/Product passes through unchanged.

    When no type-aware handler applies (Sum/Product/Tuple/Array/Set/Ref),
    the value passes through without being interpreted as [tag, payload].
    This is correct because the type handlers above cover all SATS-encoded
    types — a value reaching the fallback is either a bare scalar or a
    list that doesn't need decoding.
    """
    atype = {"String": []}
    # val is a 2-element SATS pair, atype is String (not Sum/Product)
    # Falls through to pass-through fallback — returns val as-is
    result = _extract_sats_val([0, "hello"], atype)
    assert result == [0, "hello"], f"Expected [0, 'hello'], got {result!r}"


def test_product_empty_elements():
    """Empty Product (no fields) returns None."""
    atype = {"Product": {"elements": []}}
    assert _extract_sats_val([], atype) is None


def test_product_single_element():
    """Single-element Product unwraps to the element value."""
    atype = {
        "Product": {
            "elements": [
                {"name": {"some": "name"}, "algebraic_type": {"String": []}}
            ]
        }
    }
    assert _extract_sats_val(["alice"], atype) == "alice"


def test_product_multi_element():
    """Multi-element Product returns list of field values."""
    atype = {
        "Product": {
            "elements": [
                {"name": {"some": "x"}, "algebraic_type": {"U64": []}},
                {"name": {"some": "y"}, "algebraic_type": {"U64": []}},
                {"name": {"some": "z"}, "algebraic_type": {"U64": []}},
            ]
        }
    }
    assert _extract_sats_val([1, 2, 3], atype) == [1, 2, 3]


def test_tuple_type():
    """Tuple type returns list of elements."""
    atype = {
        "Tuple": {
            "elements": [
                {"algebraic_type": {"String": []}},
                {"algebraic_type": {"U64": []}},
            ]
        }
    }
    result = _extract_sats_val(["hello", 42], atype)
    assert result == ["hello", 42]


def test_product_with_optional_field_some():
    """Product field that is Option<String>::Some returns the string."""
    atype = {
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
    }
    # Product([Option::Some("bob")]) → ["bob"] → [0, "bob"] as raw value
    # But at the product level, the field value is already a SATS sum: [0, "bob"]
    result = _extract_sats_val([[0, "bob"]], atype)
    # Single-element product unwraps, Option::Some unwraps
    assert result == "bob", f"Expected 'bob', got {result!r}"


def test_product_with_optional_field_none():
    """Product field that is Option<String>::None returns None."""
    atype = {
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
    }
    result = _extract_sats_val([[1, []]], atype)
    assert result is None, f"Expected None, got {result!r}"


def test_ref_type():
    """Ref type extracts the first list element."""
    atype = {"Ref": {}}
    assert _extract_sats_val(["0xabc"], atype) == "0xabc"
    assert _extract_sats_val(["0xabc", "extra"], atype) == "0xabc"


def test_ref_type_empty():
    """Ref type with empty list returns None."""
    atype = {"Ref": {}}
    assert _extract_sats_val([], atype) is None


def test_ref_type_none():
    """Ref type with scalar None returns None."""
    atype = {"Ref": {}}
    assert _extract_sats_val(None, atype) is None


def test_issue_link_status():
    """IssueLinkStatus enum (Open/Closed) returns variant name."""
    atype = {
        "Sum": {
            "variants": [
                {"name": {"some": "open"}, "algebraic_type": {"Product": {"elements": []}}},
                {"name": {"some": "closed"}, "algebraic_type": {"Product": {"elements": []}}},
            ]
        }
    }
    assert _extract_sats_val([0, []], atype) == "open"
    assert _extract_sats_val([1, []], atype) == "closed"


def test_sum_variant_payload_is_product_with_nested_types():
    """Enum variant with fields containing nested types."""
    atype = {
        "Sum": {
            "variants": [
                {
                    "name": {"some": "TaskEvent"},
                    "algebraic_type": {
                        "Product": {
                            "elements": [
                                {"name": {"some": "task_id"}, "algebraic_type": {"String": []}},
                                {
                                    "name": {"some": "old_status"},
                                    "algebraic_type": {
                                        "Sum": {
                                            "variants": [
                                                {"name": {"some": "available"}, "algebraic_type": {"Product": {"elements": []}}},
                                                {"name": {"some": "inProgress"}, "algebraic_type": {"Product": {"elements": []}}},
                                                {"name": {"some": "done"}, "algebraic_type": {"Product": {"elements": []}}},
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
    # TaskEvent { task_id: "t-1", old_status: inProgress }
    # SATS: [0, ["t-1", [1, []]]]
    result = _extract_sats_val([0, ["t-1", [1, []]]], atype)
    assert result == {"TaskEvent": ["t-1", "inProgress"]}, f"Got {result!r}"


def test_enum_variant_with_option_none_preserves_structure():
    """Enum variant with Option<String>::None field returns {name: None}, not just name."""
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
    # Assigned { assignee: None } → [0, [[1, []]]]
    result = _extract_sats_val([0, [[1, []]]], atype)
    # The variant HAS a payload (a single Option field), it just resolved to None.
    # Should NOT collapse to "Assigned" — must keep {name: None}
    assert result == {"Assigned": None}, f"Expected {{'Assigned': None}}, got {result!r}"


def test_non_zero_variant_index_fallback():
    """Legacy fallback no longer collapses to None — passes through unchanged."""
    atype = {}  # No type info available
    # With the type-aware handlers in place, the fallback no longer
    # interprets 2-element lists as [tag, payload]. The value passes
    # through as-is rather than collapsing to None.
    assert _extract_sats_val([1, "data"], atype) == [1, "data"]
