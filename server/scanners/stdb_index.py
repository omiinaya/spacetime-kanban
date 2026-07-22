"""STDB index scanner — finds missing #[index(btree)] on foreign key fields.

Scans Rust STDB modules (*.rs files in server/spacetimedb/src/) for
pub struct fields ending in _id, _name, _key, _ref, _by that lack
#[index(btree)], #[primary_key], or #[unique] annotations.

Priority: P1 (high) — missing indexes cause slow STDB queries.
"""

import os
import re

from scanners import register_scanner


def _scan_rust_file(filepath: str) -> list[dict]:
    """Scan a single Rust file for STDB table structs with missing indexes."""
    findings = []
    try:
        with open(filepath) as f:
            lines = f.readlines()
    except (OSError, UnicodeDecodeError):
        return []

    i = 0
    while i < len(lines):
        line = lines[i]
        if "#[table" not in line and not line.strip().startswith("#[table"):
            i += 1
            continue

        # Found a table — locate the struct
        struct_name = None
        brace_depth = 0
        in_struct = False
        fields = []  # (line_idx, field_name, field_type)
        attributes_before_field: list[str] = []

        # Move past #[table(...)] to find struct
        j = i
        while j < len(lines) and "pub struct" not in lines[j]:
            j += 1
        if j >= len(lines):
            i += 1
            continue

        struct_line = lines[j]
        m = re.match(r"pub struct (\w+)", struct_line)
        if m:
            struct_name = m.group(1)
        else:
            i += 1
            continue

        brace_depth = struct_line.count("{") - struct_line.count("}")
        in_struct = brace_depth > 0

        # Reset attributes for the first field
        k = j + 1

        while k < len(lines) and (in_struct or brace_depth > 0):
            current = lines[k]
            stripped = current.strip()

            # Count braces
            brace_depth += current.count("{") - current.count("}")

            if stripped.startswith("#["):
                attributes_before_field.append(stripped)
            elif stripped.startswith("pub ") and ":" in stripped:
                # This is a field
                parts = stripped.split(":", 1)
                field_name = parts[0].replace("pub ", "").strip()
                field_type = parts[1].strip().rstrip(",")

                # Check if this is a foreign key
                is_fk = any(
                    field_name.endswith(suffix)
                    for suffix in ("_id", "_name", "_key", "_ref", "_by")
                )
                if is_fk and field_name != "id":
                    # Check if it already has an index annotation
                    has_index = any(
                        "#[index(btree)]" in a or "#[unique]" in a or "#[primary_key]" in a
                        for a in attributes_before_field
                    )
                    if not has_index:
                        short_path = "/".join(filepath.split("/")[-3:])
                        fields.append(
                            {
                                "line": k + 1,
                                "field": field_name,
                                "type": field_type,
                                "struct": struct_name,
                                "file": short_path,
                            }
                        )

                attributes_before_field = []
            elif stripped.startswith("//") or stripped == "":
                pass  # comments/blank lines don't reset attributes
            else:
                # Non-attribute, non-field line (e.g. doc comment) — attributes don't carry
                if not stripped.startswith("///") and not stripped.startswith("//!"):
                    attributes_before_field = []

            if brace_depth <= 0:
                in_struct = False
            k += 1

        if fields:
            for f in fields:
                findings.append(
                    {
                        "title": f"Add #[index(btree)] to {f['struct']}.{f['field']}",
                        "description": (
                            f"STDB table `{f['struct']}` has field `{f['field']}: {f['type']}` "
                            f"without `#[index(btree)]` in {f['file']}:{f['line']}. "
                            f"This field looks like a foreign key and will be slow to query without an index."
                        ),
                        "priority": 1,
                        "scanner": "stdb_index",
                    }
                )

        i = k  # Skip past this struct

    return findings


@register_scanner
def scan_stdb_index(repo_name: str, repo_path: str) -> list[dict]:
    """Scan for STDB tables missing indexes on foreign key fields."""
    # Find all .rs files in server/spacetimedb/src/
    stdb_src = os.path.join(repo_path, "server", "spacetimedb", "src")
    if not os.path.isdir(stdb_src):
        return []

    findings = []
    for root, _dirs, files in os.walk(stdb_src):
        for f in files:
            if f.endswith(".rs"):
                filepath = os.path.join(root, f)
                findings.extend(_scan_rust_file(filepath))

    # Batched: one task per repo instead of per-field (avoids noise)
    if not findings:
        return []

    total = len(findings)
    # Group findings by file for the description
    by_file = {}
    for f in findings:
        file_key = f.get("file", "unknown").split("/", 1)[-1]
        if file_key not in by_file:
            by_file[file_key] = []
        by_file[file_key].append(f)

    file_count = len(by_file)
    field_list = "\n".join(
        f"  - `{f.get('struct', '?')}.{f.get('field', '?')}` in {f.get('file', '?')}:{f.get('line', '?')}"
        for f in findings[:20]
    )
    if len(findings) > 20:
        field_list += f"\n  ... and {len(findings) - 20} more field(s)"

    return [
        {
            "title": f"Add #[index(btree)] to {total} field(s) across {file_count} file(s) in {repo_name}",
            "description": (
                f"Found {total} foreign-key-like fields missing `#[index(btree)]` "
                f"across {file_count} file(s).\n\n"
                f"Missing indexes:\n{field_list}\n\n"
                f"Adding `#[index(btree)]` to these fields will improve STDB query performance."
            ),
            "priority": 1,
            "scanner": "stdb_index",
        }
    ]
