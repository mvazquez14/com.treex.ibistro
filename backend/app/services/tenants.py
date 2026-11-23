from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import Tenant
from app.services.slug import next_available_slug


async def allocate_unique_slug(session: AsyncSession, business_name: str) -> str:
    result = await session.exec(select(Tenant.slug))
    taken = {slug for slug in result.all() if slug}
    return next_available_slug(business_name, taken)
