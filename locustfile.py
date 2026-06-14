from locust import HttpUser, task, between

class JNTUHUser(HttpUser):
    wait_time = between(1, 5)

    @task(1)
    def health_check(self):
        self.client.get("/api/health")

    @task(2)
    def get_latest_notifications(self):
        self.client.get("/api/getlatestnotifications")

    @task(3)
    def get_academic_result(self):
        # Using the provided sample roll number
        roll_no = "18e51A0479"
        self.client.get(f"/api/getAcademicResult?rollNumber={roll_no}")

    @task(3)
    def get_backlogs(self):
        # Using the provided sample roll number
        roll_no = "18e51A0479"
        self.client.get(f"/api/getBacklogs?roll_no={roll_no}")

    @task(1)
    def get_all_results(self):
        # This might be a heavy operation
        roll_no = "18e51A0479"
        self.client.get(f"/api/getAllResult?roll_no={roll_no}")
