from __future__ import annotations
import json, logging, hashlib, hmac, datetime
import httpx
from app.core.config import settings

logger = logging.getLogger(__name__)


class SESClient:
    """AWS SES v2 client using httpx + SigV4. No boto3 needed."""

    def __init__(self):
        self.region = settings.AWS_SES_REGION
        self.access_key = settings.AWS_SES_ACCESS_KEY_ID
        self.secret_key = settings.AWS_SES_SECRET_ACCESS_KEY
        self.from_email = settings.FROM_EMAIL
        self.from_name = settings.FROM_NAME
        self.endpoint = f"https://email.{self.region}.amazonaws.com"

    def _sign(self, key: bytes, msg: str) -> bytes:
        return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()

    def _get_signing_key(self, date_stamp: str) -> bytes:
        k = self._sign(("AWS4" + self.secret_key).encode("utf-8"), date_stamp)
        k = self._sign(k, self.region)
        k = self._sign(k, "ses")
        return self._sign(k, "aws4_request")

    def _auth_headers(self, method: str, path: str, payload: str, headers: dict) -> dict:
        now = datetime.datetime.now(datetime.timezone.utc)
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        ds = now.strftime("%Y%m%d")
        canon_hdrs = "".join(f"{k.lower()}:{v.strip()}\n" for k, v in sorted(headers.items()))
        signed_hdrs = ";".join(k.lower() for k in sorted(headers.keys()))
        payload_hash = hashlib.sha256(payload.encode()).hexdigest()
        canon_req = f"{method}\n{path}\n\n{canon_hdrs}\n{signed_hdrs}\n{payload_hash}"
        scope = f"{ds}/{self.region}/ses/aws4_request"
        sts = f"AWS4-HMAC-SHA256\n{amz_date}\n{scope}\n{hashlib.sha256(canon_req.encode()).hexdigest()}"
        sig = hmac.new(self._get_signing_key(ds), sts.encode(), hashlib.sha256).hexdigest()
        auth = f"AWS4-HMAC-SHA256 Credential={self.access_key}/{scope}, SignedHeaders={signed_hdrs}, Signature={sig}"
        return {**headers, "Authorization": auth, "x-amz-date": amz_date}

    async def send_email(self, to_email: str, subject: str, html_body: str, text_body: str | None = None) -> dict:
        path = "/v2/email/outbound-emails"
        body_content = {"Html": {"Data": html_body, "Charset": "UTF-8"}}
        if text_body:
            body_content["Text"] = {"Data": text_body, "Charset": "UTF-8"}
        payload = json.dumps({
            "FromEmailAddress": f"{self.from_name} <{self.from_email}>",
            "Destination": {"ToAddresses": [to_email]},
            "Content": {"Simple": {"Subject": {"Data": subject, "Charset": "UTF-8"}, "Body": body_content}},
        })
        headers = {"Host": f"email.{self.region}.amazonaws.com", "Content-Type": "application/json"}
        signed = self._auth_headers("POST", path, payload, headers)
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(f"{self.endpoint}{path}", content=payload, headers=signed)
            if resp.status_code >= 400:
                logger.error("SES send failed (%d): %s", resp.status_code, resp.text[:500])
                resp.raise_for_status()
            logger.info("Email sent to %s: %s", to_email, subject)
            return resp.json()


ses_client = SESClient()
