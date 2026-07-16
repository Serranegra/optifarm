"""Crop rules: what makes a cell plantable.

Adding a crop means adding a module here and nothing else. If the rule is
"the neighbourhood must contain (or avoid) certain blocks", subclass
:class:`~mcfarm_opt.crops.base.AdjacencyCropRule` and declare the requirements;
if it is stranger than that, implement :class:`~mcfarm_opt.crops.base.CropRule`
directly and write the CP-SAT constraints by hand.
"""

from __future__ import annotations

from mcfarm_opt.crops.base import (
    AdjacencyCropRule,
    AdjacencyRequirement,
    CropRule,
    ObjectiveTerm,
)
from mcfarm_opt.crops.cactus import Cactus
from mcfarm_opt.crops.sugarcane import Sugarcane

__all__ = [
    "AdjacencyCropRule",
    "AdjacencyRequirement",
    "Cactus",
    "CropRule",
    "ObjectiveTerm",
    "Sugarcane",
]
