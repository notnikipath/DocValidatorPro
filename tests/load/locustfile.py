from locust import HttpUser, between, task


class GatewayUser(HttpUser):
    wait_time = between(1, 3)

    @task(3)
    def health(self):
        self.client.get("/health")

    @task(2)
    def services_health(self):
        self.client.get("/services/health")

    @task(1)
    def dashboard_overview(self):
        self.client.get("/dashboard/overview", params={"actor_role": "analyst"})
