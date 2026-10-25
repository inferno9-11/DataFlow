import random
import time
from locust import HttpUser, between, task


class DataFlowLoadTestUser(HttpUser):
    wait_time = between(0.1, 0.5)

    def on_start(self):
        """Register or authenticate user session."""
        self.user_email = f"loadtest_{int(time.time() * 1000)}_{random.randint(1000, 9999)}@dataflow.dev"
        self.password = "LoadTestPassword2026!"
        self.token = ""

        # Register
        reg_resp = self.client.post(
            "/api/v1/auth/register",
            json={
                "email": self.user_email,
                "password": self.password,
                "full_name": "Load Test Bot",
                "role": "user",
            },
        )
        if reg_resp.status_code == 201:
            # Login
            login_resp = self.client.post(
                "/api/v1/auth/login",
                json={"email": self.user_email, "password": self.password},
            )
            if login_resp.status_code == 200:
                self.token = login_resp.json().get("access_token", "")

    def get_headers(self):
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    @task(5)
    def list_records(self):
        if not self.token:
            return
        status = random.choice(["cleared", "flagged", "pending"])
        self.client.get(
            f"/api/v1/records?status={status}&page=1&page_size=25",
            headers=self.get_headers(),
            name="/api/v1/records?status=[status]",
        )

    @task(3)
    def ingest_single_record(self):
        if not self.token:
            return
        txn_id = f"txn_locust_{int(time.time() * 1000)}_{random.randint(100, 999)}"
        payload = {
            "transaction_id": txn_id,
            "account_id": f"acc_{random.randint(1, 10)}",
            "amount": round(random.uniform(10.0, 5000.0), 2),
            "currency": "USD",
            "category": random.choice(["payment", "transfer", "refund"]),
            "merchant_name": "E-Commerce Gateway",
        }
        self.client.post(
            "/api/v1/records",
            json=payload,
            headers=self.get_headers(),
            name="/api/v1/records [single]",
        )

    @task(2)
    def submit_asynchronous_batch_job(self):
        if not self.token:
            return
        batch_size = random.randint(5, 20)
        now_ts = int(time.time() * 1000)
        records = [
            {
                "transaction_id": f"batch_{now_ts}_{i}",
                "account_id": "acc_bulk_pool",
                "amount": round(random.uniform(25.0, 2500.0), 2),
                "currency": "USD",
                "category": "payment",
                "merchant_name": f"Batch Vendor {i}",
            }
            for i in range(batch_size)
        ]
        self.client.post(
            "/api/v1/jobs",
            json={"records": records, "job_type": "bulk_transaction_ingest"},
            headers=self.get_headers(),
            name="/api/v1/jobs [bulk async]",
        )

    @task(2)
    def get_analytics(self):
        if not self.token:
            return
        self.client.get(
            "/api/v1/analytics/summary",
            headers=self.get_headers(),
            name="/api/v1/analytics/summary",
        )

    @task(1)
    def health_check(self):
        self.client.get("/health/live", name="/health/live")
