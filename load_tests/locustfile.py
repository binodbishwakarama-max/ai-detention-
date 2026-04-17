"""Locust performance testing scenario for the Evaluation API.

Run locally:
    locust -f load_tests/locustfile.py --host=http://localhost:8000

Simulates a mixture of:
1. Authentication (login)
2. Config Creation
3. Evaluation Run Dispatch
4. Progress Polling
"""

from locust import HttpUser, task, between, events
import logging

class EvaluationEngineUser(HttpUser):
    wait_time = between(1, 5) # Users wait 1-5 seconds between tasks
    
    def on_start(self):
        """Executed when a simulated user starts."""
        self.access_token = None
        self.org_id = None
        
        # Login and get token
        response = self.client.post("/api/v1/auth/login", json={
            "email": "admin@example.com",
            "password": "SecurePassword123!"
        })
        
        if response.status_code == 200:
            data = response.json()
            self.access_token = data.get("access_token")
            self.headers = {"Authorization": f"Bearer {self.access_token}"}
            logging.info("User logged in successfully.")
        else:
            logging.error(f"Login failed: {response.status_code}")
            
    @task(3)
    def create_and_trigger_evaluation(self):
        """Simulate creating a config and immediately launching an eval."""
        if not self.access_token:
            return
            
        # 1. Create a config (simulated dataset ID)
        ds_id = "550e8400-e29b-41d4-a716-446655440001"
        res = self.client.post("/api/v1/evaluations/configs", headers=self.headers, json={
            "name": "Load Test Config",
            "dataset_id": ds_id,
            "model_config": {"provider": "openai", "model": "gpt-3.5-turbo"},
            "metrics_config": [{"metric_type": "accuracy", "weight": 1.0}]
        })
        
        if res.status_code == 201:
            config_id = res.json()["id"]
            
            # 2. Trigger the evaluation run
            run_res = self.client.post("/api/v1/evaluations/runs", headers=self.headers, json={
                "config_id": config_id
            })
            
            if run_res.status_code == 202:
                run_id = run_res.json()["id"]
                
                # 3. Poll for status twice
                self.client.get(f"/api/v1/evaluations/runs/{run_id}", headers=self.headers)
                self.client.get(f"/api/v1/evaluations/runs/{run_id}/results", headers=self.headers)

    @task(1)
    def view_dashboard(self):
        """Simulate viewing the dashboard list of evaluations."""
        if not self.access_token:
            return
        self.client.get("/api/v1/evaluations/runs?page=1&page_size=10", headers=self.headers)
        self.client.get("/api/v1/datasets?page=1&page_size=10", headers=self.headers)

@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Assertions to run at the end of the load test."""
    p99 = environment.stats.total.get_response_time_percentile(0.99)
    error_rate = environment.stats.total.fail_ratio
    
    # Assertions for CI
    # If using Locust as a library or in CI, we can fail the build here or via exit code
    logging.info(f"Test completed. P99: {p99}ms | Error Rate: {error_rate*100}%")
    
    if p99 > 200:
        logging.error(f"P99 latency ({p99}ms) exceeded 200ms threshold!")
    if error_rate > 0.001:
        logging.error(f"Error rate ({error_rate*100}%) exceeded 0.1% threshold!")
