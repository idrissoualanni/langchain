"""baseline

Revision ID: 6f983fd23f52
Revises:
Create Date: 2026-10-06 05:09:55.602732

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '6f983fd23f52'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # The project uses a custom schema init in backend/app/infrastructure/database/schema.py
    # This baseline migration marks the current state as 'done' without executing
    # the SQL here, as the tables are already managed by the app's startup logic.
    # If we wanted to move fully to Alembic, we would transcribe schema.py here.
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
