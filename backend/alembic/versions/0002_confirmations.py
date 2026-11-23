"""Record who posted a confirmed comment and when."""
from alembic import op
import sqlalchemy as sa

revision = '0002'
down_revision = '0001'
branch_labels = depends_on = None

def upgrade():
    op.create_table('confirmations',
                    sa.Column('operation_id', sa.String(64), primary_key=True),
                    sa.Column('username', sa.String(128)),
                    sa.Column('confirmed_at', sa.Float, nullable=False))

def downgrade():
    op.drop_table('confirmations')
