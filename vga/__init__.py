"""Video Generation Agent: prompt to 20-60s code-generated explainer, CLI only."""

from .models import DURATION_TOLERANCE, Storyboard
from .pipeline import run_project

__all__ = ["DURATION_TOLERANCE", "Storyboard", "run_project"]
