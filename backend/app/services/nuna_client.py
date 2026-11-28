"""Calls the internal iBistro routes on Nuna. Mock mode never leaves the process."""

import base64
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from app.core.config import settings

_TIMEOUT = 20.0


def _api_base() -> str:
    parts = urlsplit(settings.NUNA_TOKEN_URL)
    return f"{parts.scheme}://{parts.netloc}/api/v1"


def _authorization() -> dict[str, str]:
    raw = f"{settings.NUNA_CLIENT_ID}:{settings.NUNA_CLIENT_SECRET}".encode()
    token = base64.b64encode(raw).decode("ascii")
    return {"Authorization": f"Basic {token}"}


async def check_trial_eligibility(
    nuna_org_id: str, rfc: str, whatsapp_phone: str
) -> bool:
    if settings.MOCK_MODE:
        return True
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.post(
                f"{_api_base()}/internal/ibistro/trial-eligibility",
                json={
                    "nuna_org_id": nuna_org_id,
                    "rfc": rfc,
                    "whatsapp_phone": whatsapp_phone,
                },
                headers=_authorization(),
            )
    except httpx.HTTPError:
        return False
    if response.status_code != 200:
        return False
    body = response.json()
    return bool(body.get("eligible"))


async def revoke_trial_eligibility(
    nuna_org_id: str, rfc: str, whatsapp_phone: str
) -> None:
    if settings.MOCK_MODE:
        return
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            await client.post(
                f"{_api_base()}/internal/ibistro/revoke-trial",
                json={
                    "nuna_org_id": nuna_org_id,
                    "rfc": rfc,
                    "whatsapp_phone": whatsapp_phone,
                },
                headers=_authorization(),
            )
    except httpx.HTTPError:
        return


async def sync_organization_profile(
    *,
    nuna_org_id: str,
    business_name: str,
    rfc: str,
    address: str,
    whatsapp_phone: str,
    logo_path: Path | None,
) -> None:
    if settings.MOCK_MODE:
        return
    data = {
        "nuna_org_id": nuna_org_id,
        "business_name": business_name,
        "rfc": rfc,
        "address": address,
        "whatsapp_phone": whatsapp_phone,
    }
    files = None
    if logo_path is not None and logo_path.is_file():
        suffix = logo_path.suffix.lower()
        content_type = {".png": "image/png", ".webp": "image/webp"}.get(
            suffix, "image/jpeg"
        )
        files = {
            "logo": (logo_path.name, logo_path.read_bytes(), content_type),
        }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            await client.post(
                f"{_api_base()}/internal/ibistro/organization-profile",
                data=data,
                files=files,
                headers=_authorization(),
            )
    except httpx.HTTPError:
        return
