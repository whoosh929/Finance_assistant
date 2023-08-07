"""migration 2023-08-02_22-06-08

Revision ID: ba8dd7de69b4
Revises: 
Create Date: 2023-08-02 22:06:09.125311

"""
from alembic import op
import sqlalchemy as sa
import pgvector


# revision identifiers, used by Alembic.
revision = 'ba8dd7de69b4'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('conversation_role_types',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('role_type', sa.String(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('age', sa.Integer(), nullable=True),
    sa.Column('location', sa.String(), nullable=True),
    sa.Column('email', sa.String(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('email')
    )
    op.create_table('conversations',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('record_created', sa.DateTime(), nullable=False),
    sa.Column('interaction_id', sa.Uuid(), nullable=False),
    sa.Column('conversation_role_type_id', sa.Integer(), nullable=True),
    sa.Column('conversation_text', sa.String(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('additional_metadata', sa.String(), nullable=True),
    sa.Column('embedding', pgvector.sqlalchemy.Vector(dim=1536), nullable=True),
    sa.Column('exception', sa.String(), nullable=True),
    sa.Column('is_deleted', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['conversation_role_type_id'], ['conversation_role_types.id'], ),
    sa.ForeignKeyConstraint(['conversation_role_type_id'], ['conversation_role_types.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('documents',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('record_created', sa.DateTime(), nullable=False),
    sa.Column('document_text', sa.String(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('additional_metadata', sa.String(), nullable=True),
    sa.Column('embedding', pgvector.sqlalchemy.Vector(dim=1536), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('conversations',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('record_created', sa.DateTime(), nullable=False),
    sa.Column('conversation_text', sa.String(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('interaction_id', sa.Uuid(), nullable=True),
    sa.Column('additional_metadata', sa.String(), nullable=True),
    sa.Column('embedding', pgvector.sqlalchemy.Vector(dim=1536), nullable=True),
    sa.Column('is_deleted', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('user_settings',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('setting_name', sa.String(), nullable=False),
    sa.Column('setting_value', sa.String(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('user_settings')
    op.drop_table('conversations')
    op.drop_table('documents')
    op.drop_table('conversations')
    op.drop_table('users')
    op.drop_table('conversation_role_types')
    # ### end Alembic commands ###
