"""Offline deterministic multivolume geometry experiment."""

from .assembly import GENERATOR_ID, GENERATOR_VERSION, generate_multivolume_experiment
from .model import ExperimentResult

__all__ = [
    "ExperimentResult",
    "GENERATOR_ID",
    "GENERATOR_VERSION",
    "generate_multivolume_experiment",
]
