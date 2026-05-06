"""Register all ORM models with SQLAlchemy's metadata.

Import every model module here to ensure that all table definitions are loaded
before Alembic generates migrations or the application creates database sessions.
"""

from app.models.user import User
from app.models.job import Job
from app.models.application_tracker_entry import ApplicationTrackerEntry

__all__ = ["User", "Job", "ApplicationTrackerEntry"]
