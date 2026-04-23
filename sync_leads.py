"""
sync_leads.py — Tutorii chatbot lead importer
Runs as a Railway cron job every 5 minutes.
Reads unprovisioned leads from MongoDB and creates Tutorii accounts.
"""
import os
import sys
import pymongo
import httpx

MONGO_URI   = os.environ["MONGODB_URI"]
BACKEND     = os.environ.get("BACKEND_URL", "https://backend-tut-production.up.railway.app/api/v1")
ADMIN_EMAIL = os.environ["ADMIN_EMAIL"]
ADMIN_PASS  = os.environ["ADMIN_PASSWORD"]


def get_token() -> str:
    res = httpx.post(f"{BACKEND}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=10)
    res.raise_for_status()
    return res.json()["access_token"]


def get_password(email: str) -> str:
    username = email.split("@")[0]
    base = username.capitalize()
    return base if len(base) >= 8 else base + "12345"


def sync():
    token = get_token()
    headers = {"Authorization": f"Bearer {token}"}

    mongo = pymongo.MongoClient(MONGO_URI)
    col = mongo["tutorii_chatbot"]["chat_users"]

    leads = list(col.find({
        "accountProvisioned": False,
        "agentEmail": {"$exists": True, "$ne": None, "$ne": ""}
    }))

    if not leads:
        print("No pending leads.")
        mongo.close()
        return

    created = skipped = failed = 0

    for lead in leads:
        email = lead.get("agentEmail", "").strip().lower()
        if not email or "@" not in email:
            continue

        username = email.split("@")[0]
        password = get_password(email)

        try:
            res = httpx.post(
                f"{BACKEND}/admin/users/create",
                headers=headers,
                json={
                    "email": email,
                    "full_name": username.capitalize(),
                    "password": password,
                    "role": "user"
                },
                timeout=10
            )

            if res.status_code in (200, 201):
                col.update_one({"_id": lead["_id"]}, {"$set": {"accountProvisioned": True}})
                print(f"✓ Created: {email} (password: {password})")
                created += 1

            elif res.status_code == 400:
                col.update_one({"_id": lead["_id"]}, {"$set": {"accountProvisioned": True}})
                print(f"→ Skipped (already exists): {email}")
                skipped += 1

            else:
                print(f"✗ Failed ({res.status_code}): {email} — {res.text}")
                failed += 1

        except Exception as e:
            print(f"✗ Error for {email}: {e}")
            failed += 1

    print(f"\nDone — {created} created, {skipped} skipped, {failed} failed")
    mongo.close()


if __name__ == "__main__":
    sync()
