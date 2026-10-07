"""The kinds of value a load can meet that the reviewed tables don't recognise.

One fixed list, so the loader, the places module and anything reading the load report all
use the same words.
"""

from __future__ import annotations

from enum import StrEnum


class Unrecognised(StrEnum):
    SUBSTATION_SPELLING = "substation spelling"
    BOTTLENECK_LIST_POINT = "bottleneck-list point"
    UPGRADE_LINK = "upgrade link"
    STUDY_PROGRESS = "study progress"
    BATCH_2023_VALUE = "2023-batch value"
    UPGRADE_COST = "upgrade cost"
    BOTTLENECK_COST = "bottleneck cost"
