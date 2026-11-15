"""Release-gate thresholds. Scoring uses integer comparisons, not rounded percents."""

HARD_THRESHOLD_PERCENT = 100
SOFT_THRESHOLD_PERCENT = 85
DATASET_VERSION = "r6.3"


def meets_threshold(passed: int, total: int, threshold_percent: int) -> bool:
    """True when ``passed / total`` is at least ``threshold_percent`` percent.

    ``16/20`` is 80 and fails an 85% bar. ``17/20`` meets it. Nothing is rounded up.
    """
    if total <= 0:
        return False
    return passed * 100 >= total * threshold_percent
