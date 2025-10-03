from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db

router = APIRouter()


@router.post("/", status_code=status.HTTP_201_CREATED, response_model=schemas.OrderRead)
async def create_order(payload: schemas.OrderCreate, db: Session = Depends(get_db)):
    if not payload.items:
        raise HTTPException(status_code=400, detail="Order must include at least one item")

    order = models.Order(table_id=payload.table_id)

    if payload.user_id is not None:
        user = db.query(models.User).filter(models.User.id == payload.user_id).first()
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")
        order.user_id = user.id

    total_quantity = 0
    total_amount = Decimal("0")

    for item in payload.items:
        item_price = Decimal(str(item.unit_price))
        total_quantity += item.quantity
        total_amount += item_price * item.quantity

        order_item = models.OrderItem(
            product_id=item.product_id,
            name=item.name,
            unit_price=item_price,
            quantity=item.quantity,
        )
        order.items.append(order_item)

    order.total_quantity = total_quantity
    order.total_amount = total_amount

    db.add(order)
    db.commit()
    db.refresh(order)

    return order


@router.get("/", response_model=list[schemas.OrderRead])
async def list_orders(db: Session = Depends(get_db)):
    orders = db.query(models.Order).order_by(models.Order.created_at.desc()).all()
    return orders


@router.delete("/{order_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_order(order_id: int, db: Session = Depends(get_db)):
    order = db.query(models.Order).filter(models.Order.id == order_id).first()
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")

    db.delete(order)
    db.commit()

    return None


@router.patch("/{order_id}/status", response_model=schemas.OrderRead)
async def update_order_status(
    order_id: int,
    status_payload: schemas.OrderStatusUpdate,
    db: Session = Depends(get_db),
):
    order = db.query(models.Order).filter(models.Order.id == order_id).first()
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")

    order.status = status_payload.status
    db.commit()
    db.refresh(order)

    return order
