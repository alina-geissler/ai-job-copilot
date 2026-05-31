"""Register all ORM models with SQLAlchemy's metadata.

Import every model module here to ensure that all table definitions are loaded
before Alembic generates migrations or the application creates database sessions.
"""

from app.models.user import User
from app.models.job import Job
from app.models.application_tracker_entry import ApplicationTrackerEntry
from app.models.document import Document
from app.models.profile_information import ProfileInformation
from app.models.search_profile import SearchProfile
from app.models.search_run import SearchRun
from app.models.search_run_job import SearchRunJob
from app.models.manual_job_posting import ManualJobPosting
from app.models.job_normalization import JobNormalization
from app.models.cover_letter import CoverLetter
from app.models.cover_letter_snapshot import CoverLetterSnapshot

__all__ = [
    "User", "Job", "ApplicationTrackerEntry", "Document", "ProfileInformation",
    "SearchProfile", "SearchRun", "SearchRunJob",
    "ManualJobPosting", "JobNormalization", "CoverLetter", "CoverLetterSnapshot",
]
