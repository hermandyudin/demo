import requests
import time
import json

API_BASE_URL = "http://localhost:8002"  # API Service URL
USER_ID = "test_user"


# -------------------------------
# 1. Get JWT Token
# -------------------------------
def get_token():
    response = requests.post(f"{API_BASE_URL}/token", json={"user_id": USER_ID})
    if response.status_code != 200:
        raise Exception(f"Failed to get token: {response.text}")
    token = response.json()["token"]
    print(f"[+] Token received: {token}")
    return token


# -------------------------------
# 2. Get Active Models
# -------------------------------
def get_models():
    response = requests.get(f"{API_BASE_URL}/models")
    if response.status_code != 200:
        raise Exception(f"Failed to get models: {response.text}")

    models = response.json()
    print(f"[+] Active models: {json.dumps(models, indent=2)}")
    return models


# -------------------------------
# 3. Get Model Schema
# -------------------------------
def get_schema(model_name):
    response = requests.get(f"{API_BASE_URL}/schema/{model_name}")
    if response.status_code != 200:
        raise Exception(f"Failed to get schema: {response.text}")

    schema = response.json()
    print(f"[+] Schema for {model_name}: {json.dumps(schema, indent=2)}")
    return schema


# -------------------------------
# 4. Send Task to Model
# -------------------------------
def send_task(token, model_name, data):
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/octet-stream"}

    response = requests.post(f"{API_BASE_URL}/task/{model_name}", headers=headers, data=data)
    if response.status_code != 200:
        raise Exception(f"Failed to send task: {response.text}")

    task_id = response.json()["task_id"]
    print(f"[+] Task submitted! Task ID: {task_id}")
    return task_id


# -------------------------------
# 5. Get Task Result
# -------------------------------
def get_task_status(token, task_id):
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(f"{API_BASE_URL}/task/{task_id}", headers=headers)

    if response.status_code == 404:
        print("[*] Task not ready yet...")
        return None

    if response.status_code != 200:
        raise Exception(f"Failed to get task status: {response.text}")

    result = response.json()
    return result


# -------------------------------
# MAIN FLOW
# -------------------------------
def main():
    # Step 1: Get token
    # token = get_token()

    # Step 2: Get models
    models = get_models()
    model_name = "ModelA"

    if not model_name in models:
        print("[-] No model A available")
        return

    # Step 3: Get schema
    schema = get_schema(model_name)

    # Step 4: Prepare request based on schema
    # import models_pb2
    #
    # if model_name == "ModelA":
    #     request = models_pb2.ModelARequest()
    #     request.message = "Hello from API!"
    # elif model_name == "ModelB":
    #     request = models_pb2.ModelBRequest()
    #     request.value = 42
    # else:
    #     raise Exception(f"Unknown model: {model_name}")
    #
    # serialized_request = request.SerializeToString()
    #
    # # Step 5: Send task
    # task_id = send_task(token, model_name, serialized_request)
    #
    # # Step 6: Poll for result
    # print("[*] Waiting for result...")
    # for _ in range(10):
    #     result = get_task_status(token, task_id)
    #     if result:
    #         print(f"[+] Task result: {result}")
    #         break
    #     time.sleep(1)
    # else:
    #     print("[-] Task timed out")


if __name__ == "__main__":
    main()