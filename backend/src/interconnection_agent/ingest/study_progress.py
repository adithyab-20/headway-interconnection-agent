"""How far a CAISO project got through the operator's process, as reviewed configuration.

The operator studies each batch of projects twice before anyone signs: a first, rough study
of the grid upgrades needed and what they'd cost, then a second, detailed one. CAISO's file
records each project's status in three columns (first study, second study, agreement). This
table turns those raw cells into one plain value, the furthest step reached:

  * ``Agreement signed``   - the agreement to connect is executed
  * ``Second study done``  - the detailed study is complete ("SGIA" is the small-project
                             agreement stage, past that study)
  * ``First study done``   - the rough study is complete ("Facilities Study" in the first
                             column means the project already moved on to the next study)
  * ``No study done``      - none complete ("Re-Study" means one is being redone)
  * ``Not applicable``     - the project used a process without these studies

Any raw value not listed here is reported and left empty: never guessed.
"""

from __future__ import annotations

AGREEMENT_SIGNED = "Agreement signed"
SECOND_STUDY_DONE = "Second study done"
FIRST_STUDY_DONE = "First study done"
NO_STUDY_DONE = "No study done"
NOT_APPLICABLE = "Not applicable"

# Every raw value seen in each column, and what it means. Blank cells read as "".
FIRST_STUDY: dict[str, str] = {
    "Complete": "done",
    "Facilities Study": "done",
    "None": "not done",
    "": "not done",
    "Re-Study": "not done",
    "NA": "not applicable",
    "N/A": "not applicable",
    "Waived": "not applicable",
}
SECOND_STUDY: dict[str, str] = {
    "Complete": "done",
    "SGIA": "done",
    "None": "not done",
    "": "not done",
    "Re-Study": "not done",
    "NA": "not applicable",
}
AGREEMENT: dict[str, str] = {
    "Executed": "signed",
    "": "not signed",
    "In Progress": "not signed",
    "Filed Unexecuted": "not signed",
    "Terminated": "signed",  # an agreement can only be terminated after it was signed
}


def furthest_step(first: str, second: str, agreement: str) -> tuple[str | None, list[str]]:
    """Return the furthest step reached, and any raw values the table doesn't know.

    When any value is unknown the step is ``None``: the project's progress is reported for
    review rather than worked out from the columns we do understand.
    """
    unknown = [
        value
        for value, table in ((first, FIRST_STUDY), (second, SECOND_STUDY), (agreement, AGREEMENT))
        if value not in table
    ]
    if unknown:
        return None, unknown
    if AGREEMENT[agreement] == "signed":
        return AGREEMENT_SIGNED, []
    if SECOND_STUDY[second] == "done":
        return SECOND_STUDY_DONE, []
    if FIRST_STUDY[first] == "done":
        return FIRST_STUDY_DONE, []
    if FIRST_STUDY[first] == SECOND_STUDY[second] == "not applicable":
        return NOT_APPLICABLE, []
    return NO_STUDY_DONE, []
