"""add_products_orders_audit_logs

T04：products / audit_logs / orders（03 §1）。
- orders schema 前置（T04 DELETE 守卫需查订单存在性；业务逻辑 T06）。
- products.updated_at 由 trigger 维护（03 约定，沿用 set_updated_at()）。

Revision ID: 6c6729d82d9f
Revises: f48c716731a7
Create Date: 2026-11-10 15:50:39.171776

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "6c6729d82d9f"
down_revision = "f48c716731a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "products",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("subtitle", sa.String(length=255), nullable=True),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("tags", sa.ARRAY(sa.Text()), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("price_cents", sa.BigInteger(), nullable=False),
        sa.Column("original_price_cents", sa.BigInteger(), nullable=True),
        sa.Column("cover_image", sa.String(length=512), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("file_name", sa.String(length=255), nullable=True),
        sa.Column("file_url", sa.String(length=512), nullable=True),
        sa.Column("file_size", sa.BigInteger(), nullable=True),
        sa.Column("preview_media", sa.JSON(), server_default=sa.text("'[]'::json"), nullable=False),
        sa.Column("is_listed", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("price_cents > 0", name="ck_products_price_positive"),
        sa.CheckConstraint(
            "original_price_cents IS NULL OR original_price_cents >= price_cents",
            name="ck_products_original_gte_price",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_products_listed_created", "products", ["is_listed", sa.text("created_at DESC")])
    op.create_index("ix_products_category", "products", ["category"])
    op.create_index("ix_products_listed_price", "products", ["is_listed", "price_cents"])

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("admin_id", sa.BigInteger(), nullable=True),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("target_type", sa.String(length=32), nullable=True),
        sa.Column("target_id", sa.BigInteger(), nullable=True),
        sa.Column("reason", sa.String(length=200), nullable=True),
        sa.Column("ip", postgresql.INET(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["admin_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_logs_admin_created", "audit_logs", ["admin_id", sa.text("created_at DESC")])
    op.create_index("ix_audit_logs_action_created", "audit_logs", ["action", sa.text("created_at DESC")])

    op.create_table(
        "orders",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("order_no", sa.String(length=24), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("product_title_snapshot", sa.String(length=120), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("original_cents", sa.BigInteger(), nullable=False),
        sa.Column("coupon_code", sa.String(length=32), nullable=True),
        sa.Column("discount_cents", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("pay_status", sa.String(length=16), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("pay_channel", sa.String(length=16), nullable=True),
        sa.Column("paid_submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paid_note", sa.String(length=500), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoke_reason", sa.String(length=200), nullable=True),
        sa.Column("expire_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("pay_status IN ('pending','paid','revoked','cancelled')", name="ck_orders_pay_status"),
        sa.CheckConstraint(
            "pay_channel IS NULL OR pay_channel IN ('wechat','alipay')", name="ck_orders_pay_channel"
        ),
        sa.CheckConstraint("amount_cents >= 0", name="ck_orders_amount_nonneg"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_no"),
    )
    op.create_index("ix_orders_user_paystatus", "orders", ["user_id", "pay_status"])
    op.create_index("ix_orders_paystatus_submitted", "orders", ["pay_status", "paid_submitted_at"])
    op.create_index("ix_orders_product", "orders", ["product_id"])

    # products.updated_at trigger（03 约定）
    op.execute(
        """
CREATE TRIGGER trg_products_updated_at
BEFORE UPDATE ON products
FOR EACH ROW EXECUTE FUNCTION set_updated_at();
"""
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_products_updated_at ON products;")
    op.drop_index("ix_orders_product", table_name="orders")
    op.drop_index("ix_orders_paystatus_submitted", table_name="orders")
    op.drop_index("ix_orders_user_paystatus", table_name="orders")
    op.drop_table("orders")
    op.drop_index("ix_audit_logs_action_created", table_name="audit_logs")
    op.drop_index("ix_audit_logs_admin_created", table_name="audit_logs")
    op.drop_table("audit_logs")
    op.drop_index("ix_products_listed_price", table_name="products")
    op.drop_index("ix_products_category", table_name="products")
    op.drop_index("ix_products_listed_created", table_name="products")
    op.drop_table("products")
