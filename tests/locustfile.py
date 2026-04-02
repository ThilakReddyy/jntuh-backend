"""
JNTUH Backend – Locust Stress Test
====================================
Run (web UI):
    locust -f tests/locustfile.py --host http://localhost:8000

Run (headless / CI):
    locust -f tests/locustfile.py --host http://localhost:8000 \
           --headless -u 100 -r 10 --run-time 2m

User classes
------------
- LightUser       → quick health / notification polls (high frequency)
- ResultUser      → typical student looking up their results
- HeavyUser       → power-user hitting every endpoint including class results & contrast
- NotificationUser→ notification-focused traffic
"""

import random
from locust import HttpUser, SequentialTaskSet, TaskSet, between, task, events

# ---------------------------------------------------------------------------
# Realistic sample roll numbers (B.Tech 4-year pattern: YYBRANCHSN)
# Use a wide spread so requests don't all hit the same cache entry.
# ---------------------------------------------------------------------------
SERIES = [
    "25YF1A05",
    "24XW5A05",
    "23WN1R00",
    "22W85A02",
    "21VE1A66",
    "19VJ1R00",
    "18E51A04",
]

SAMPLE_rollNumberS = [f"{series}{i:02d}" for series in SERIES for i in range(1, 100)]


CONTRAST_PAIRS = [
    ("20B91A0501", "20B91A0502"),
    ("19B91A0501", "19B91A0502"),
    ("21B91A0501", "21B91A0502"),
    ("20B91A1201", "20B91A1202"),
]

NOTIFICATION_CATEGORIES = ["all", "results", "exams", "others"]
REGULATIONS = ["R18", "R22", "R20", "R16"]
DEGREES = ["btech", "mtech", "mba", "mca"]
YEARS = ["1", "2", "3", "4"]


def random_roll() -> str:
    return random.choice(SAMPLE_rollNumberS)


def random_contrast_pair():
    return random.choice(CONTRAST_PAIRS)


# ---------------------------------------------------------------------------
# Task Sets
# ---------------------------------------------------------------------------


class HealthTasks(TaskSet):
    """Lightweight ping – used by all user types to simulate keep-alive checks."""

    @task
    def health_check(self):
        with self.client.get(
            "/api/health", name="/api/health", catch_response=True
        ) as r:
            if r.status_code == 200:
                r.success()
            else:
                r.failure(f"Health check failed: {r.status_code}")


class NotificationTasks(TaskSet):
    """Notification-related endpoints."""

    @task(5)
    def get_notifications_default(self):
        with self.client.get(
            "/api/notifications",
            params={"page": 1, "category": "all"},
            name="/api/notifications [all]",
            catch_response=True,
        ) as r:
            if r.status_code in (200, 404):
                r.success()
            else:
                r.failure(f"Unexpected status: {r.status_code}")

    @task(3)
    def get_notifications_filtered(self):
        params = {
            "page": random.randint(1, 3),
            "category": random.choice(NOTIFICATION_CATEGORIES),
            "regulation": random.choice(REGULATIONS),
            "degree": random.choice(DEGREES),
        }
        with self.client.get(
            "/api/notifications",
            params=params,
            name="/api/notifications [filtered]",
            catch_response=True,
        ) as r:
            if r.status_code in (200, 404):
                r.success()
            else:
                r.failure(f"Unexpected status: {r.status_code}")

    @task(2)
    def get_latest_notifications(self):
        with self.client.get(
            "/api/getlatestnotifications",
            name="/api/getlatestnotifications",
            catch_response=True,
        ) as r:
            if r.status_code in (200, 404):
                r.success()
            else:
                r.failure(f"Unexpected status: {r.status_code}")

    @task(1)
    def stop(self):
        self.interrupt()


class ResultTasks(TaskSet):
    """Core result-fetching endpoints."""

    @task(5)
    def get_academic_result(self):
        roll = random_roll()
        with self.client.get(
            "/api/getAcademicResult",
            params={"rollNumber": roll},
            name="/api/getAcademicResult",
            catch_response=True,
        ) as r:
            if r.status_code in (200, 202, 404, 422):
                r.success()
            else:
                r.failure(f"Unexpected status {r.status_code} for roll {roll}")

    @task(4)
    def get_all_result(self):
        roll = random_roll()
        with self.client.get(
            "/api/getAllResult",
            params={"rollNumber": roll},
            name="/api/getAllResult",
            catch_response=True,
        ) as r:
            if r.status_code in (200, 202, 404, 422):
                r.success()
            else:
                r.failure(f"Unexpected status {r.status_code} for roll {roll}")

    @task(3)
    def get_backlogs(self):
        roll = random_roll()
        with self.client.get(
            "/api/getBacklogs",
            params={"rollNumber": roll},
            name="/api/getBacklogs",
            catch_response=True,
        ) as r:
            if r.status_code in (200, 202, 404, 422):
                r.success()
            else:
                r.failure(f"Unexpected status {r.status_code} for roll {roll}")

    @task(2)
    def get_credits_checker(self):
        roll = random_roll()
        with self.client.get(
            "/api/getCreditsChecker",
            params={"rollNumber": roll},
            name="/api/getCreditsChecker",
            catch_response=True,
        ) as r:
            if r.status_code in (200, 202, 404, 422):
                r.success()
            else:
                r.failure(f"Unexpected status {r.status_code} for roll {roll}")

    @task(1)
    def stop(self):
        self.interrupt()


class GraceMarksTasks(TaskSet):
    """Grace marks endpoints."""

    @task(2)
    def check_eligibility(self):
        roll = random_roll()
        with self.client.get(
            "/api/grace-marks/eligibility",
            params={"rollNumber": roll},
            name="/api/grace-marks/eligibility",
            catch_response=True,
        ) as r:
            if r.status_code in (200, 202, 404, 422):
                r.success()
            else:
                r.failure(f"Unexpected status {r.status_code}")

    @task(1)
    def get_proof(self):
        roll = random_roll()
        with self.client.get(
            "/api/grace-marks/proof",
            params={"rollNumber": roll},
            name="/api/grace-marks/proof",
            catch_response=True,
        ) as r:
            if r.status_code in (200, 404, 422):
                r.success()
            else:
                r.failure(f"Unexpected status {r.status_code}")

    @task(1)
    def stop(self):
        self.interrupt()


class HeavyUserTaskSet(SequentialTaskSet):
    """
    Sequential flow that mimics a power-user browsing many endpoints in order.
    Uses SequentialTaskSet so the journey is deterministic per iteration.
    """

    def on_start(self):
        self.roll = random_roll()
        pair = random_contrast_pair()
        self.roll_a, self.roll_b = pair

    @task
    def step_health(self):
        self.client.get("/api/health", name="/api/health [heavy]")

    @task
    def step_notifications(self):
        self.client.get(
            "/api/notifications",
            params={"page": 1, "category": "results"},
            name="/api/notifications [heavy]",
        )

    @task
    def step_academic_result(self):
        self.client.get(
            "/api/getAcademicResult",
            params={"rollNumber": self.roll},
            name="/api/getAcademicResult [heavy]",
        )

    @task
    def step_all_result(self):
        self.client.get(
            "/api/getAllResult",
            params={"rollNumber": self.roll},
            name="/api/getAllResult [heavy]",
        )

    @task
    def step_backlogs(self):
        self.client.get(
            "/api/getBacklogs",
            params={"rollNumber": self.roll},
            name="/api/getBacklogs [heavy]",
        )

    @task
    def step_credits(self):
        self.client.get(
            "/api/getCreditsChecker",
            params={"rollNumber": self.roll},
            name="/api/getCreditsChecker [heavy]",
        )

    @task
    def step_contrast(self):
        self.client.get(
            "/api/getResultContrast",
            params={"rollNumber1": self.roll_a, "rollNumber2": self.roll_b},
            name="/api/getResultContrast [heavy]",
        )

    @task
    def step_class_results(self):
        self.client.get(
            "/api/getClassResults",
            params={"rollNumber": self.roll, "type": "academicresult"},
            name="/api/getClassResults [heavy]",
        )

    @task
    def step_grace_eligibility(self):
        self.client.get(
            "/api/grace-marks/eligibility",
            params={"rollNumber": self.roll},
            name="/api/grace-marks/eligibility [heavy]",
        )


# ---------------------------------------------------------------------------
# User Classes
# ---------------------------------------------------------------------------


class LightUser(HttpUser):
    """
    Simulates lightweight traffic: students refreshing health / notifications.
    High spawn count – represents majority of real traffic.
    """

    weight = 5
    wait_time = between(2, 5)
    tasks = {HealthTasks: 3, NotificationTasks: 7}


class ResultUser(HttpUser):
    """
    Simulates a typical student checking their results.
    Medium weight – core API traffic.
    """

    weight = 10
    wait_time = between(3, 8)
    tasks = {ResultTasks: 8, HealthTasks: 2}


class GraceMarksUser(HttpUser):
    """
    Simulates students specifically checking grace marks eligibility.
    Lower weight – niche feature.
    """

    weight = 2
    wait_time = between(4, 10)
    tasks = {GraceMarksTasks: 9, HealthTasks: 1}


class NotificationUser(HttpUser):
    """
    Simulates users polling for notifications (frontend polling strategy).
    """

    weight = 3
    wait_time = between(1, 4)
    tasks = {NotificationTasks: 9, HealthTasks: 1}


class HeavyUser(HttpUser):
    """
    Simulates a power-user or a crawler hitting every endpoint in sequence.
    Low weight – rare but resource-intensive.
    """

    weight = 1
    wait_time = between(5, 15)
    tasks = [HeavyUserTaskSet]


# ---------------------------------------------------------------------------
# Optional: contrast + hard-refresh as standalone tasks (low frequency)
# ---------------------------------------------------------------------------


class ContrastUser(HttpUser):
    """
    Simulates users running result comparisons between two students.
    """

    weight = 1
    wait_time = between(10, 20)

    @task
    def get_contrast(self):
        roll_a, roll_b = random_contrast_pair()
        with self.client.get(
            "/api/getResultContrast",
            params={"rollNumber": roll_a, "rollNumber2": roll_b},
            name="/api/getResultContrast",
            catch_response=True,
        ) as r:
            if r.status_code in (200, 404, 422):
                r.success()
            else:
                r.failure(f"Unexpected status {r.status_code}")

    @task
    def health(self):
        self.client.get("/api/health", name="/api/health")


# ---------------------------------------------------------------------------
# Event hooks – print a summary banner on test start
# ---------------------------------------------------------------------------


@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    print("\n" + "=" * 60)
    print("  JNTUH Backend Locust Stress Test Starting")
    print(f"  Target host : {environment.host}")
    print(f"  Roll samples: {len(SAMPLE_rollNumberS)}")
    print("=" * 60 + "\n")


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    print("\n" + "=" * 60)
    print("  JNTUH Backend Locust Stress Test Finished")
    stats = environment.stats.total
    print(f"  Total requests : {stats.num_requests}")
    print(f"  Failures       : {stats.num_failures}")
    if stats.num_requests:
        print(
            f"  Failure rate   : {stats.num_failures / stats.num_requests * 100:.2f}%"
        )
    print(f"  Avg response   : {stats.avg_response_time:.1f} ms")
    print(f"  95th pct       : {stats.get_response_time_percentile(0.95):.1f} ms")
    print(f"  99th pct       : {stats.get_response_time_percentile(0.99):.1f} ms")
    print("=" * 60 + "\n")
