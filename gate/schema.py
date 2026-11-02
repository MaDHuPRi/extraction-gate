"""The eight W-2 boxes under test, and what a mistake in each one costs."""
from dataclasses import dataclass, field

FIELDS = ["box1", "box2", "box3", "box4", "box5", "box6", "box16", "box17"]

FIELD_NAMES = {
    "box1": "Box 1 Wages",
    "box2": "Box 2 Federal tax withheld",
    "box3": "Box 3 Social Security wages",
    "box4": "Box 4 Social Security tax",
    "box5": "Box 5 Medicare wages",
    "box6": "Box 6 Medicare tax",
    "box16": "Box 16 State wages",
    "box17": "Box 17 State tax withheld",
}

# Dollars of tax effect per $1 of extraction error. These are my assumptions, not tax advice.
# Withheld amounts feed a return dollar for dollar. Wages only move tax by a marginal rate
# (22% assumed), and Box 3, 5 and 16 by less. A tax reviewer should own these numbers.
DEFAULT_WEIGHTS = {
    "box1": 0.22,
    "box2": 1.0,
    "box3": 0.062,
    "box4": 1.0,
    "box5": 0.0145,
    "box6": 1.0,
    "box16": 0.05,
    "box17": 1.0,
}


@dataclass
class GateConfig:
    weights: dict = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))
    critical_weight: float = 1.0      # a field this heavy counts as critical
    review_cost: float = 10.0         # a blank value goes to a person, so it costs review time
    max_added_risk: float = 25.0      # dollars at risk may rise by this much across the test set
    max_layout_drop: float = 0.02     # no layout may lose more than this much accuracy
    pinned_docs: list = field(default_factory=list)  # reviewer-confirmed documents must fully pass

    def critical_fields(self):
        return {f for f, w in self.weights.items() if w >= self.critical_weight}
