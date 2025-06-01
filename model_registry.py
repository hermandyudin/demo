from fastapi import FastAPI, HTTPException
import json
import os
import requests
import time
import threading
from prometheus_client import Gauge
from utils.rabbitmq_monitoring import fetch_queue_sizes

REGISTRY_FILE = "models_registry.json"

ACTIVE_MODELS = Gauge("active_models_total", "Number of active models")
MODEL_NAMES = Gauge("active_model", "Active model label", ['model_name'])
app = FastAPI()

# Load models from file (persistent storage)
if os.path.exists(REGISTRY_FILE):
    with open(REGISTRY_FILE, "r") as f:
        try:
            models = json.load(f)
        except json.JSONDecodeError:
            models = {}
else:
    models = {}


# Save models to file
def save_registry():
    with open(REGISTRY_FILE, "w") as f:
        json.dump(models, f)


def update_metrics():
    ACTIVE_MODELS.set(len(models))
    MODEL_NAMES.clear()
    for name in models:
        MODEL_NAMES.labels(model_name=name).set(1)


async def poll_queue_sizes():
    while True:
        fetch_queue_sizes()
        time.sleep(10)


@app.get("/models")
def get_models():
    """Return a list of active models"""
    return models


@app.post("/register")
def register_model(model_name: str, host: str, port: int):
    """Register a new model in the registry"""
    models[model_name] = {"host": host, "port": port, "last_ping": time.time()}
    save_registry()
    update_metrics()
    return {"message": f"Model {model_name} registered successfully."}


@app.post("/unregister")
def unregister_model(model_name: str):
    """Unregister a model"""
    if model_name in models:
        del models[model_name]
        save_registry()
        update_metrics()
        return {"message": f"Model {model_name} removed from registry."}
    raise HTTPException(status_code=404, detail="Model not found.")


# Health check (removes dead models)
async def health_check():
    while True:
        time.sleep(10)  # Run every 10 seconds
        for model_name in list(models.keys()):
            host, port = models[model_name]["host"], models[model_name]["port"]
            try:
                response = requests.get(f"http://{host}:{port}/ping", timeout=3)
                if response.status_code == 200:
                    models[model_name]["last_ping"] = time.time()
                else:
                    unregister_model(model_name)
            except requests.exceptions.RequestException:
                unregister_model(model_name)
        save_registry()


# Start health check thread
threading.Thread(target=health_check, daemon=True).start()
threading.Thread(target=poll_queue_sizes, daemon=True).start()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=9000)
