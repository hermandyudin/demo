from locust import HttpUser, task, between
import json
import base64
import time

USERNAME = "testuser"
PASSWORD = "testpassword"

MODEL_NAME = "ModelA"  # Replace with an actual model registered in your system


class APIUser(HttpUser):
    wait_time = between(1, 3)  # Simulates user "think time"

    def on_start(self):
        """Runs when a simulated user starts: register (if needed) and login."""
        self.token = None

        # Login
        response = self.client.post("/login", json={"username": USERNAME, "password": PASSWORD})
        if response.status_code == 200:
            self.token = response.json()["access_token"]
        else:
            print("Login failed!")

    @task
    def submit_task_and_check_result(self):
        if not self.token:
            return

        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }

        # Example input — replace with your actual expected JSON input
        request_body = {
            "messages": [
                "Message 1",
                "Message 2"
            ],
            "context": [
                {
                    "value1": "Value 1.1",
                    "value2": "Value 1.2",
                    "con": "Some context",
                    "v": [
                        1, 2, 3, 4
                    ]
                },
                {
                    "value1": "Value 2.1",
                    "value2": "Value 2.2",
                    "con": "Some context 2",
                    "v": [
                        5, 6, 7, 8
                    ]
                }
            ]
        }

        # Submit task
        response = self.client.post(f"/models/{MODEL_NAME}/tasks", json=request_body, headers=headers)
        if response.status_code != 200:
            print(f"Failed to submit task: {response.text}")
            return

        task_id = response.json()["task_id"]
        time.sleep(2)  # Wait a bit before polling for result

        # Check task result (polling a few times max)
        for _ in range(5):
            result_response = self.client.get(
                f"/models/{MODEL_NAME}/result", params={"task_id": task_id},
                headers={"Authorization": f"Bearer {self.token}"}
            )
            if result_response.status_code == 200:
                print(f"Task completed: {result_response.json()}")
                break
            elif result_response.status_code == 202:
                print("Task still in progress...")
                time.sleep(1)
            else:
                print(f"Error fetching result: {result_response.status_code}")
                break
