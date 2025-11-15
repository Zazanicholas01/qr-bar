from datetime import datetime
from decimal import Decimal
from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import relationship
from sqlalchemy.schema import UniqueConstraint

from .database import Base


class Table(Base):
    __tablename__ = "tables"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(80), unique=True, nullable=False)
    name = Column(String(120), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    users = relationship("User", back_populates="table", foreign_keys="User.table_ref_id")
    orders = relationship("Order", back_populates="table", foreign_keys="Order.table_ref_id")


class StaffUser(Base):
    __tablename__ = "staff_users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(120), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(50), nullable=False, default="admin")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False)
    email = Column(String(200), nullable=True)
    password_hash = Column(String(255), nullable=True)
    email_verified_at = Column(DateTime, nullable=True)
    phone = Column(String(30), nullable=True)
    age = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    table_ref_id = Column(Integer, ForeignKey("tables.id", ondelete="SET NULL"), nullable=True)
    table_code = Column(String(80), nullable=True)

    orders = relationship("Order", back_populates="user")
    table = relationship("Table", back_populates="users", foreign_keys=[table_ref_id])

    @property
    def table_id(self) -> str | None:
        return self.table.code if self.table else self.table_code


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    status = Column(String(50), default="pending", nullable=False)
    total_quantity = Column(Integer, default=0, nullable=False)
    total_amount = Column(Numeric(10, 2), default=Decimal("0"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    table_ref_id = Column(Integer, ForeignKey("tables.id", ondelete="SET NULL"), nullable=True)
    table_code = Column(String(80), nullable=True)
    user = relationship("User", back_populates="orders")
    table = relationship("Table", back_populates="orders", foreign_keys=[table_ref_id])
    items = relationship(
        "OrderItem",
        back_populates="order",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    transaction = relationship(
        "Transaction",
        back_populates="order",
        cascade="all, delete-orphan",
        uselist=False,
    )

    @property
    def table_id(self) -> str | None:
        if self.table and self.table.code:
            return self.table.code
        return self.table_code


class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    product_id = Column(Integer, nullable=False)
    name = Column(String(200), nullable=False)
    unit_price = Column(Numeric(10, 2), nullable=False)
    quantity = Column(Integer, nullable=False)

    order = relationship("Order", back_populates="items")


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id", ondelete="CASCADE"), unique=True, nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)
    method = Column(String(50), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    order = relationship("Order", back_populates="transaction")


# =====================
# Inventory core models
# =====================

class InventoryItem(Base):
    __tablename__ = "inventory_items"

    id = Column(Integer, primary_key=True)
    sku = Column(String(80), unique=True, nullable=False, index=True)
    name = Column(String(200), nullable=False)
    unit = Column(String(16), nullable=False, default="pcs")  # e.g., ml, g, pcs
    par_level = Column(Numeric(12, 3), nullable=True)
    reorder_point = Column(Numeric(12, 3), nullable=True)
    starting_stock_qty = Column(Numeric(12, 3), nullable=True)
    alert_threshold_qty = Column(Numeric(12, 3), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class InventoryLocation(Base):
    __tablename__ = "inventory_locations"

    id = Column(Integer, primary_key=True)
    name = Column(String(120), unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class Recipe(Base):
    __tablename__ = "recipes"

    # product_id maps to OrderItem.product_id (sellable menu item)
    product_id = Column(Integer, primary_key=True)
    yield_qty = Column(Numeric(12, 3), nullable=False, default=1)
    yield_unit = Column(String(16), nullable=False, default="pcs")


class RecipeComponent(Base):
    __tablename__ = "recipe_components"

    id = Column(Integer, primary_key=True)
    recipe_item_id = Column(Integer, ForeignKey("recipes.product_id", ondelete="CASCADE"), nullable=False)
    component_item_id = Column(Integer, ForeignKey("inventory_items.id", ondelete="RESTRICT"), nullable=False)
    qty_per_yield = Column(Numeric(12, 3), nullable=False)
    unit = Column(String(16), nullable=False)


class StockMovement(Base):
    __tablename__ = "stock_movements"

    id = Column(Integer, primary_key=True)
    item_id = Column(Integer, ForeignKey("inventory_items.id", ondelete="RESTRICT"), nullable=False)
    location_id = Column(Integer, ForeignKey("inventory_locations.id", ondelete="SET NULL"), nullable=True)
    qty_delta = Column(Numeric(12, 3), nullable=False)
    unit = Column(String(16), nullable=False)
    reason = Column(String(24), nullable=False)  # sale, receive, adjust, waste, transfer
    ref_type = Column(String(24), nullable=True)  # e.g., order, po, adjust
    ref_id = Column(Integer, nullable=True)
    occurred_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_by = Column(String(120), nullable=True)

    __table_args__ = (
        # Helps idempotency for per-order movements
        UniqueConstraint("item_id", "reason", "ref_type", "ref_id", name="uq_movement_idem"),
    )


class StockLevel(Base):
    __tablename__ = "stock_levels"

    item_id = Column(Integer, ForeignKey("inventory_items.id", ondelete="CASCADE"), primary_key=True)
    location_id = Column(Integer, ForeignKey("inventory_locations.id", ondelete="CASCADE"), primary_key=True, nullable=False)
    qty_on_hand_cached = Column(Numeric(12, 3), nullable=False, default=0)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class Supplier(Base):
    __tablename__ = "suppliers"

    id = Column(Integer, primary_key=True)
    name = Column(String(200), unique=True, nullable=False)
    lead_time_hours = Column(Integer, nullable=True)
    contact_email = Column(String(200), nullable=True)
    notes = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    products = relationship("SupplierProduct", back_populates="supplier", cascade="all, delete-orphan")


class SupplierProduct(Base):
    __tablename__ = "supplier_products"

    id = Column(Integer, primary_key=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False)
    inventory_item_id = Column(Integer, ForeignKey("inventory_items.id", ondelete="CASCADE"), nullable=False)
    price_per_unit = Column(Numeric(12, 2), nullable=True)
    unit = Column(String(16), nullable=True)
    min_qty = Column(Numeric(12, 3), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    supplier = relationship("Supplier", back_populates="products")
    inventory_item = relationship("InventoryItem")

    __table_args__ = (
        UniqueConstraint("supplier_id", "inventory_item_id", name="uq_supplier_product"),
    )


class SupplyOrder(Base):
    __tablename__ = "supply_orders"

    id = Column(Integer, primary_key=True)
    inventory_item_id = Column(Integer, ForeignKey("inventory_items.id", ondelete="SET NULL"), nullable=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True)
    state = Column(String(24), nullable=False, default="alert")
    suggested_qty = Column(Numeric(12, 3), nullable=False)
    unit = Column(String(16), nullable=False, default="pcs")
    price_per_unit = Column(Numeric(12, 2), nullable=True)
    total_price = Column(Numeric(12, 2), nullable=True)
    sla_hours = Column(Numeric(8, 2), nullable=True)
    alert_triggered_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    acknowledged_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    inventory_item = relationship("InventoryItem")
    supplier = relationship("Supplier")


# =====================
# Auth/session models
# =====================

class AuthSession(Base):
    __tablename__ = "auth_sessions"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash = Column(String(128), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    revoked_at = Column(DateTime, nullable=True)
    user_agent = Column(String(255), nullable=True)
    ip = Column(String(64), nullable=True)


class EmailToken(Base):
    __tablename__ = "email_tokens"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    purpose = Column(String(16), nullable=False)  # verify | reset
    token_hash = Column(String(128), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    consumed_at = Column(DateTime, nullable=True)
