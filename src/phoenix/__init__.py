"""Person 1's data and recommendation building blocks. No network calls at import."""

from .integration import build_recommendations
from .models import Job, Rental, UserProfile

__all__ = ["Job", "Rental", "UserProfile", "build_recommendations"]
