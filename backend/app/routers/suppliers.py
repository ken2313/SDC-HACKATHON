"""Supplier management (Feature 6).

Who may do what (checked by the backend):
  view suppliers, price lists, order history ..... suppliers:view    (Owner, Employee)
  add / edit / deactivate suppliers, set prices .. suppliers:manage  (OWNER ONLY)

There is no delete endpoint on purpose: a supplier's order history must stay.
Deactivate a supplier instead.
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth.permissions import PERM_SUPPLIERS_MANAGE, PERM_SUPPLIERS_VIEW, require_permission
from app.database import get_db
from app.models import User
from app.schemas.supplier import (
    ProductWithoutSupplier,
    SupplierCreate,
    SupplierDetail,
    SupplierListItem,
    SupplierProductCreate,
    SupplierProductResult,
    SupplierProductUpdate,
    SupplierSummary,
    SupplierUpdate,
)
from app.services import supplier_service as service
from app.services.supplier_service import SupplierError

router = APIRouter(prefix="/api/suppliers", tags=["Suppliers"])

DbSession = Annotated[Session, Depends(get_db)]
Viewer = Annotated[User, Depends(require_permission(PERM_SUPPLIERS_VIEW))]
Manager = Annotated[User, Depends(require_permission(PERM_SUPPLIERS_MANAGE))]  # OWNER ONLY


def _http(error: SupplierError) -> HTTPException:
    return HTTPException(status_code=error.status_code, detail=error.message)


# NOTE: fixed paths (/summary, /products-without-supplier) must be declared before /{supplier_id}.

@router.get("", response_model=list[SupplierListItem])
def list_suppliers(
    db: DbSession,
    user: Viewer,
    include_inactive: bool = False,
    search: str | None = Query(default=None, max_length=100),
):
    return service.list_suppliers(db, user.business_id, include_inactive, search)


@router.get("/summary", response_model=SupplierSummary)
def suppliers_summary(db: DbSession, user: Viewer):
    return service.get_summary(db, user.business_id)


@router.get("/products-without-supplier", response_model=list[ProductWithoutSupplier])
def products_without_supplier(db: DbSession, user: Viewer):
    """Products no active supplier sells. They cannot get a purchase order draft until one does."""
    return service.products_without_supplier(db, user.business_id)


@router.post("", response_model=SupplierDetail, status_code=201)
def create_supplier(data: SupplierCreate, db: DbSession, user: Manager):
    try:
        return service.create_supplier(db, user, data)
    except SupplierError as error:
        raise _http(error)


@router.get("/{supplier_id}", response_model=SupplierDetail)
def get_supplier(supplier_id: int, db: DbSession, user: Viewer):
    """Contact details, price list, order history and delivery statistics."""
    try:
        return service.get_supplier(db, user.business_id, supplier_id)
    except SupplierError as error:
        raise _http(error)


@router.patch("/{supplier_id}", response_model=SupplierDetail)
def update_supplier(supplier_id: int, data: SupplierUpdate, db: DbSession, user: Manager):
    try:
        return service.update_supplier(db, user, supplier_id, data)
    except SupplierError as error:
        raise _http(error)


@router.post("/{supplier_id}/deactivate", response_model=SupplierDetail)
def deactivate_supplier(supplier_id: int, db: DbSession, user: Manager):
    try:
        return service.set_active(db, user, supplier_id, active=False)
    except SupplierError as error:
        raise _http(error)


@router.post("/{supplier_id}/activate", response_model=SupplierDetail)
def activate_supplier(supplier_id: int, db: DbSession, user: Manager):
    try:
        return service.set_active(db, user, supplier_id, active=True)
    except SupplierError as error:
        raise _http(error)


@router.post("/{supplier_id}/products", response_model=SupplierProductResult, status_code=201)
def add_supplier_product(supplier_id: int, data: SupplierProductCreate, db: DbSession, user: Manager):
    try:
        return service.add_product(db, user, supplier_id, data)
    except SupplierError as error:
        raise _http(error)


@router.patch("/{supplier_id}/products/{link_id}", response_model=SupplierDetail)
def update_supplier_product(
    supplier_id: int, link_id: int, data: SupplierProductUpdate, db: DbSession, user: Manager
):
    try:
        return service.update_product(db, user, supplier_id, link_id, data)
    except SupplierError as error:
        raise _http(error)


@router.delete("/{supplier_id}/products/{link_id}", response_model=SupplierDetail)
def remove_supplier_product(supplier_id: int, link_id: int, db: DbSession, user: Manager):
    try:
        return service.remove_product(db, user, supplier_id, link_id)
    except SupplierError as error:
        raise _http(error)
