"""Define the SQLAlchemy declarative base for all ORM models.

Provide a single ``Base`` class that every database model inherits from, allowing
SQLAlchemy to register and manage all table definitions from one central metadata object.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Serve as the common base class for all ORM model definitions.

    Inherit from this class in every model module to register the model
    with SQLAlchemy's metadata and enable schema generation via Alembic.
    """
    pass


from app.models import *             # noqa
