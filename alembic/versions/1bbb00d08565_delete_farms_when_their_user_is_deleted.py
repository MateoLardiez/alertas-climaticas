"""delete farms when their user is deleted

Revision ID: 1bbb00d08565
Revises: 87a999ab8818
Create Date: 2026-10-25 21:37:09.114959

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1bbb00d08565'
down_revision: Union[str, Sequence[str], None] = '87a999ab8818'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_constraint('farm_user_id_fkey', 'farm', type_='foreignkey')
    op.create_foreign_key(
        'farm_user_id_fkey', 'farm', 'users', ['user_id'], ['id'], ondelete='CASCADE'
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('farm_user_id_fkey', 'farm', type_='foreignkey')
    op.create_foreign_key('farm_user_id_fkey', 'farm', 'users', ['user_id'], ['id'])
