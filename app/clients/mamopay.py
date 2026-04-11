from __future__ import annotations
import httpx
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

class MamoPayClient:
    """MamoPay REST API client for payment links and bank transfers."""

    def __init__(self):
        self.base_url = settings.MAMOPAY_BASE_URL.rstrip("/")
        self.headers = {
            "Authorization": f"Bearer {settings.MAMOPAY_API_KEY}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        url = f"{self.base_url}{path}"
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.request(method, url, headers=self.headers, **kwargs)
            resp.raise_for_status()
            return resp.json()

    async def create_payment_link(
        self, amount: float, title: str, description: str = "",
        customer_email: str = "", customer_name: str = "",
        external_id: str = "", is_recurring: bool = True,
    ) -> dict:
        payload = {
            "title": title, "description": description,
            "capacity": 1, "amount": amount, "amount_currency": "AED",
            "active": True, "external_id": external_id,
            "enable_customer_details": True, "send_customer_receipt": True,
            "email": customer_email,
        }
        if is_recurring:
            payload["is_recurring"] = True
            payload["frequency"] = "monthly"
        return await self._request("POST", "/links", json=payload)

    async def get_payment_link(self, link_id: str) -> dict:
        return await self._request("GET", f"/links/{link_id}")

    async def deactivate_payment_link(self, link_id: str) -> dict:
        return await self._request("PATCH", f"/links/{link_id}", json={"active": False})

    async def get_transactions(self, link_id: str | None = None) -> dict:
        path = f"/links/{link_id}/transactions" if link_id else "/transactions"
        return await self._request("GET", path)

    async def create_transfer(
        self, amount: float, iban: str, recipient_name: str,
        reason: str = "Tutorii referral commission payout", external_id: str = "",
    ) -> dict:
        payload = {
            "disbursements": [
                {
                    "first_name_or_business_name": recipient_name,
                    "account": iban,
                    "transfer_method": "BANK_ACCOUNT",
                    "reason": reason,
                    "amount": str(amount),
                }
            ]
        }
        result = await self._request("POST", "/disbursements", json=payload)
        # API returns a list — return the first item so callers get a single dict
        if isinstance(result, list) and result:
            item = result[0]
        else:
            item = result
        logger.debug("MamoPay disbursement raw response: %s", item)
        return item

    async def get_transfer(self, transfer_id: str) -> dict:
        return await self._request("GET", f"/disbursements/{transfer_id}")

mamopay_client = MamoPayClient()
