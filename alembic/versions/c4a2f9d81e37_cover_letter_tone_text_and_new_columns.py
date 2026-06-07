"""cover_letter tone TEXT migration and new generation columns

Revision ID: c4a2f9d81e37
Revises: 73043a5d9a39
Create Date: 2026-06-06 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4a2f9d81e37'
down_revision: Union[str, Sequence[str], None] = '73043a5d9a39'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    1. Convert ``cover_letters.tone`` from the ``coverlettertone`` PostgreSQL
       enum type to plain ``TEXT``.
    2. Drop the now-unused ``coverlettertone`` enum type.
    3. Data-migrate old uppercase enum values to the new lowercase tone keys:
       FORMAL → formell, NEUTRAL → sachlich, CASUAL → locker.
    4. Add seven new nullable TEXT columns that the LLM generation pipeline
       reads: ``no_gos``, ``earliest_start_date``, ``salary_expectation``,
       ``industry_group``, ``hierarchy_level``, ``output_language``,
       ``company_context``.
    """
    # Step 1: convert enum column to TEXT (USING cast keeps existing values)
    op.execute(
        "ALTER TABLE cover_letters ALTER COLUMN tone TYPE TEXT USING tone::text"
    )

    # Step 2: drop the old enum type (no longer referenced)
    op.execute("DROP TYPE IF EXISTS coverlettertone")

    # Step 3: remap old uppercase enum labels to new tone keys
    op.execute(
        """
        UPDATE cover_letters
           SET tone = CASE
                        WHEN tone = 'FORMAL'  THEN 'formell'
                        WHEN tone = 'NEUTRAL' THEN 'sachlich'
                        WHEN tone = 'CASUAL'  THEN 'locker'
                        ELSE 'formell'
                      END
        """
    )

    # Step 4: add new generation columns
    op.add_column('cover_letters', sa.Column('no_gos', sa.Text(), nullable=True))
    op.add_column('cover_letters', sa.Column('earliest_start_date', sa.Text(), nullable=True))
    op.add_column('cover_letters', sa.Column('salary_expectation', sa.Text(), nullable=True))
    op.add_column('cover_letters', sa.Column('industry_group', sa.Text(), nullable=True))
    op.add_column('cover_letters', sa.Column('hierarchy_level', sa.Text(), nullable=True))
    op.add_column('cover_letters', sa.Column('output_language', sa.Text(), nullable=True))
    op.add_column('cover_letters', sa.Column('company_context', sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema.

    Reverse the upgrade: drop the seven new columns, remap tone keys back to
    uppercase enum labels, recreate the ``coverlettertone`` enum type, and
    convert the column back to that enum type.
    """
    # Drop new columns (reverse order of addition)
    op.drop_column('cover_letters', 'company_context')
    op.drop_column('cover_letters', 'output_language')
    op.drop_column('cover_letters', 'hierarchy_level')
    op.drop_column('cover_letters', 'industry_group')
    op.drop_column('cover_letters', 'salary_expectation')
    op.drop_column('cover_letters', 'earliest_start_date')
    op.drop_column('cover_letters', 'no_gos')

    # Remap tone keys back to uppercase enum labels
    op.execute(
        """
        UPDATE cover_letters
           SET tone = CASE
                        WHEN tone = 'formell'  THEN 'FORMAL'
                        WHEN tone = 'sachlich' THEN 'NEUTRAL'
                        WHEN tone = 'locker'   THEN 'CASUAL'
                        WHEN tone = 'warm'     THEN 'FORMAL'
                        ELSE 'FORMAL'
                      END
        """
    )

    # Recreate the enum type
    op.execute("CREATE TYPE coverlettertone AS ENUM ('FORMAL', 'NEUTRAL', 'CASUAL')")

    # Convert column back to enum
    op.execute(
        "ALTER TABLE cover_letters ALTER COLUMN tone TYPE coverlettertone"
        " USING tone::coverlettertone"
    )
