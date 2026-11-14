"""Initial schema."""
from alembic import op
import sqlalchemy as sa
revision = '0001'
down_revision = None
branch_labels = depends_on = None

def upgrade():
    op.create_table('accounts', sa.Column('user_id',sa.String(64),primary_key=True), sa.Column('instagram_id',sa.String(64),nullable=False), sa.Column('username',sa.String(128),nullable=False), sa.Column('token',sa.Text,nullable=False), sa.Column('expires',sa.Float,nullable=False), sa.Column('permissions',sa.Text,nullable=False))
    op.create_table('operations', sa.Column('id',sa.String(64),primary_key=True), sa.Column('user_id',sa.String(64),nullable=False), sa.Column('fingerprint',sa.String(64),nullable=False), sa.Column('post_url',sa.Text,nullable=False), sa.Column('message',sa.Text,nullable=False), sa.Column('media_id',sa.String(64)), sa.Column('comment_id',sa.String(128)), sa.Column('status',sa.String(32),nullable=False), sa.Column('reason',sa.Text), sa.Column('error_category',sa.String(64)), sa.Column('created_at',sa.Float,nullable=False), sa.Column('demo',sa.Boolean,nullable=False))
    op.create_index('ix_operations_user_id','operations',['user_id'])
def downgrade():
    op.drop_table('operations'); op.drop_table('accounts')
