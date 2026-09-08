"""Locust load test against the deployed FastAPI plagiarism detection API.

Tests the *deployed* system over real HTTP (not the in-process pipeline
calls Reports 01-04 measure), so it captures network/queueing overhead
those in-process numbers can't see. Per Section 3.12.3: ramp concurrent
users, assert p95 latency and failure rate at a target concurrency level.

Usage:
    locust -f locustfile.py --host=http://<vm-ip>:8000 --headless \
        --users 20 --spawn-rate 2 --run-time 3m --csv results
"""

import os
import random

from locust import HttpUser, task, between

API_KEY = os.environ.get("API_KEY", "dev-secret-key-change-in-production")

# Small pool of distinct texts so repeated submissions aren't byte-identical
# (avoids any accidental content-hash-based short-circuiting) while staying
# fast to generate -- realistic submission sizes for this corpus are short
# (see Report 00's dataset reconciliation, short-answer style texts).
SAMPLE_TEXTS = [
    "Dynamic programming is a method for efficiently solving a broad range "
    "of search and optimization problems which exhibit the characteristics "
    "of overlapping subproblems and optimal substructure.",
    "Cloud computing is the delivery of computing services including "
    "servers, storage, databases, networking, software, and analytics over "
    "the Internet to offer faster innovation and flexible resources.",
    "The vector space model represents documents as vectors in a "
    "multi-dimensional space where each dimension corresponds to a "
    "separate term, commonly weighted using tf-idf scoring.",
    "Machine learning is a subset of artificial intelligence that provides "
    "systems the ability to automatically learn and improve from "
    "experience without being explicitly programmed.",
    "Blockchain technology is a decentralized distributed ledger that "
    "records transactions across many computers so that records cannot "
    "be altered retroactively without altering all subsequent blocks.",
]


class SubmissionUser(HttpUser):
    wait_time = between(1, 3)

    def on_start(self):
        self.headers = {"Authorization": f"Bearer {API_KEY}"}

    @task
    def submit_and_poll(self):
        text = random.choice(SAMPLE_TEXTS)
        filename = f"loadtest_{random.randint(0, 10**9)}.txt"

        files = {"file": (filename, text.encode("utf-8"), "text/plain")}
        with self.client.post(
            "/api/v1/submissions/",
            files=files,
            headers=self.headers,
            name="/api/v1/submissions/ [POST]",
            catch_response=True,
        ) as resp:
            if resp.status_code != 202:
                resp.failure(f"unexpected status {resp.status_code}: {resp.text[:200]}")
                return
            submission_id = resp.json().get("id")

        if not submission_id:
            return

        self.client.get(
            f"/api/v1/submissions/{submission_id}/status",
            headers=self.headers,
            name="/api/v1/submissions/{id}/status [GET]",
        )

    @task(3)
    def health_check(self):
        # Weighted higher: a lightweight request mixed in with submissions,
        # matching realistic traffic (status polling, health probes) rather
        # than testing submission-creation load in isolation.
        self.client.get("/api/v1/health/live", name="/api/v1/health/live [GET]")
