"""Chances, waits, and who's ahead: the product's main numbers.

See docs/specs/product-spec.md, ticket "Chances, waits, and who's ahead".
"""

from interconnection_agent.chances.ahead import MWAhead, WaitingProject, realistic_mw_ahead
from interconnection_agent.chances.backtest import Backtest, Band, Prediction, backtest
from interconnection_agent.chances.estimate import (
    Chance,
    NotEnoughHistory,
    Outcome,
    PastProject,
    chance_of_reaching_operation,
    chance_of_still_being_built,
)
from interconnection_agent.chances.groups import (
    AreaKind,
    ComparisonGroup,
    Odds,
    ProjectType,
    SizeBand,
    odds_for,
)

__all__ = [
    "Backtest",
    "Band",
    "Prediction",
    "backtest",
    "AreaKind",
    "Chance",
    "ComparisonGroup",
    "MWAhead",
    "WaitingProject",
    "realistic_mw_ahead",
    "ProjectType",
    "SizeBand",
    "Odds",
    "odds_for",
    "NotEnoughHistory",
    "Outcome",
    "PastProject",
    "chance_of_reaching_operation",
    "chance_of_still_being_built",
]
