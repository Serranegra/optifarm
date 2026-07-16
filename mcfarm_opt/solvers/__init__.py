"""Solvers: how the layout model is searched.

Today only the exact CP-SAT solver exists. Heuristic solvers, for terrains
where proving optimality is too slow, will implement the same
:class:`~mcfarm_opt.solvers.base.Solver` protocol.
"""

from __future__ import annotations

from mcfarm_opt.solvers.base import Solver
from mcfarm_opt.solvers.ilp import ILPSolver

__all__ = ["ILPSolver", "Solver"]
