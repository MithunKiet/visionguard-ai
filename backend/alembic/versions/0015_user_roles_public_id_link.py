"""user_roles: drop BaseEntity columns, key on parent public_ids directly

identity.user_roles is a pure link table — it doesn't need its own
surrogate id/audit trail. Replaces (user_id int, role_code str) with
(UserPublicId, RolePublicId) — both VARCHAR(36) referencing the parent
tables' public_id columns directly — as a composite primary key.

Revision ID: 0015
Revises: 0014
Create Date: 2026-07-08
"""
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('ALTER TABLE identity.user_roles ADD COLUMN "UserPublicId" VARCHAR(36)')
    op.execute('ALTER TABLE identity.user_roles ADD COLUMN "RolePublicId" VARCHAR(36)')

    op.execute('''
        UPDATE identity.user_roles ur SET "UserPublicId" = u.public_id
        FROM identity.users u WHERE ur.user_id = u.id
    ''')
    op.execute('''
        UPDATE identity.user_roles ur SET "RolePublicId" = r.public_id
        FROM roles r WHERE ur.role_code = r.code
    ''')

    op.execute('ALTER TABLE identity.user_roles ALTER COLUMN "UserPublicId" SET NOT NULL')
    op.execute('ALTER TABLE identity.user_roles ALTER COLUMN "RolePublicId" SET NOT NULL')

    # Drop old constraints before dropping the columns they reference
    op.execute('''
        DO $$
        DECLARE r RECORD;
        BEGIN
            FOR r IN
                SELECT conname FROM pg_constraint
                WHERE conrelid = 'identity.user_roles'::regclass
            LOOP
                EXECUTE format('ALTER TABLE identity.user_roles DROP CONSTRAINT %I', r.conname);
            END LOOP;
        END $$;
    ''')

    for col in (
        "id", "public_id", "is_active", "is_approved", "created_by", "created_at",
        "updated_by", "updated_at", "deleted_by", "deleted_at", "developer_remark",
        "user_id", "role_code",
    ):
        op.execute(f'ALTER TABLE identity.user_roles DROP COLUMN IF EXISTS "{col}"')

    op.execute('ALTER TABLE identity.user_roles ADD PRIMARY KEY ("UserPublicId", "RolePublicId")')
    op.execute('''
        ALTER TABLE identity.user_roles
        ADD CONSTRAINT user_roles_user_public_id_fkey
        FOREIGN KEY ("UserPublicId") REFERENCES identity.users(public_id) ON DELETE CASCADE
    ''')
    op.execute('''
        ALTER TABLE identity.user_roles
        ADD CONSTRAINT user_roles_role_public_id_fkey
        FOREIGN KEY ("RolePublicId") REFERENCES roles(public_id) ON DELETE RESTRICT
    ''')


def downgrade() -> None:
    raise NotImplementedError(
        "0015 is not reversible — restore from a pre-migration backup instead."
    )
