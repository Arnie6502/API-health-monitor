"""Endpoint configuration CRUD — add/remove the APIs you want monitored."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import AsyncSessionLocal
from ..models import Endpoint
from .schemas import EndpointCreate, EndpointOut

router = APIRouter(prefix="/endpoints", tags=["endpoints"])


async def get_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session


@router.get("", response_model=list[EndpointOut])
async def list_endpoints(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Endpoint).order_by(Endpoint.id))
    return result.scalars().all()


@router.post("", response_model=EndpointOut, status_code=201)
async def create_endpoint(
    payload: EndpointCreate, session: AsyncSession = Depends(get_session)
):
    endpoint = Endpoint(**payload.model_dump())
    session.add(endpoint)
    try:
        await session.commit()
    except Exception:
        await session.rollback()
        raise HTTPException(
            status_code=409, detail="Endpoint name already exists"
        ) from None
    await session.refresh(endpoint)
    return endpoint


@router.delete("/{endpoint_id}", status_code=204)
async def delete_endpoint(endpoint_id: int, session: AsyncSession = Depends(get_session)):
    endpoint = await session.get(Endpoint, endpoint_id)
    if endpoint is None:
        raise HTTPException(status_code=404, detail="Endpoint not found")
    await session.delete(endpoint)
    await session.commit()
