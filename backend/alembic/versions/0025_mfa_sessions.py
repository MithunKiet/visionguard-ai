"""Encrypted authenticator enrollment and session invalidation."""
from alembic import op
import sqlalchemy as sa

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade():
    for column in [sa.Column("totp_secret", sa.String(500)),
                   sa.Column("totp_pending_secret", sa.String(500)),
                   sa.Column("totp_pending_until", sa.DateTime(timezone=True)),
                   sa.Column("totp_last_step", sa.BigInteger()),
                   sa.Column("auth_version", sa.String(36), nullable=False, server_default="")]:
        op.add_column("users", column, schema="identity")

    op.execute("""CREATE FUNCTION audit.reject_audit_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'Audit records are append-only'; END; $$""")
    op.execute("""CREATE TRIGGER audit_append_only BEFORE UPDATE OR DELETE OR TRUNCATE ON audit.audit_log
        FOR EACH STATEMENT EXECUTE FUNCTION audit.reject_audit_mutation()""")


def downgrade():
    op.execute("DROP TRIGGER audit_append_only ON audit.audit_log")
    op.execute("DROP FUNCTION audit.reject_audit_mutation()")
    for column in ["auth_version", "totp_last_step", "totp_pending_until", "totp_pending_secret", "totp_secret"]:
        op.drop_column("users", column, schema="identity")
