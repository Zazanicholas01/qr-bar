from datetime import datetime
from decimal import Decimal
from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import relationship

from .database import Base


class Table(Base):
    __tablename__ = "tables"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(80), unique=True, nullable=False)
    name = Column(String(120), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    users = relationship("User", back_populates="table", foreign_keys="User.table_ref_id")
    orders = relationship("Order", back_populates="table", foreign_keys="Order.table_ref_id")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False)
    email = Column(String(200), unique=True, nullable=True)
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
