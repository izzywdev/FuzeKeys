"""Add gender field to identity model

Revision ID: c2019ga02d9g
Revises: b1908fa01c8f
Create Date: 2024-01-01 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c2019ga02d9g'
down_revision = 'b1908fa01c8f'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add gender field to identities table
    op.add_column('identities', sa.Column('encrypted_gender', sa.Text(), nullable=True))


def downgrade() -> None:
    # Remove gender field from identities table
    op.drop_column('identities', 'encrypted_gender')
