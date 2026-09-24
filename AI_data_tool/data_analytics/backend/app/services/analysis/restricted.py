"""What to tell a viewer whose own access is why an analysis cannot run.

Every analysis here refuses politely when it has too little data, and says why in
useful detail: "need at least 30 rows with a value for 'final_grade'; this has 1".
For an author that sentence is exactly right — it tells them what to do next.

For a viewer narrowed by a row rule it is wrong twice. It presents row-level
security working correctly as a failure of the data, and it leaks: the count of
their own slice and the threshold together tell them a larger population exists
behind the filter. The rules hide rows; the message should not describe them.

Found by opening a dataset as a student restricted to their own record. The page
showed three red errors, all of them the platform behaving exactly as configured.
"""
from __future__ import annotations

#: One wording for every shortfall, deliberately. Four differently-worded
#: apologies would invite a reader to compare them and infer the thresholds back.
_RESTRICTED = ("This analysis needs more rows than your access to this dataset "
               "allows, so it cannot run for you. Nothing is wrong with the data.")


def explain_shortfall(message: str, restricted: bool) -> str:
    """The message to show, given whether the asker's own view is narrowed.

    `restricted` is true when a row rule applied to this user for this dataset —
    the caller has already resolved it, so this stays a pure string decision.
    """
    if not restricted or not message:
        return message
    return _RESTRICTED
