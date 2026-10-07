"""A reviewed table that gives one spelling two different names is refused, not resolved."""

from __future__ import annotations

import pytest

from interconnection_agent.poi import AliasTable


def test_rejects_a_key_mapped_to_two_different_canonical_names() -> None:
    with pytest.raises(ValueError, match="conflict"):
        AliasTable.from_rows(
            [
                ("Midway 230 kV", "Midway 230 kV"),
                ("MIDWAY 230kV", "Midway Substation 230 kV"),
            ]
        )
