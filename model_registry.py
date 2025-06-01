from fastapi import FastAPI, HTTPException
import json
import os
import requests
import time
import threading
from prometheus_client import Gauge, generate_latest, CONTENT_TYPE_LATEST
from utils.rabbitmq_monitoring import fetch_queue_sizes
from fastapi.responses import Response

REGISTRY_FILE = "models_registry.json"

ACTIVE_MODELS = Gauge("active_models_total", "Number of active models")
MODEL_NAMES = Gauge("active_model", "Active model label", ['model_name'])

app = FastAPI()

if os.path.exists(REGISTRY_FILE):
    with open(REGISTRY_FILE, "r") as f:
        try:
            models = json.load(f)
        except json.JSONDecodeError:
            models = {}
else:
    models = {}


def save_registry():
    with open(REGISTRY_FILE, "w") as f:
        json.dump(models, f)


def update_metrics():
    ACTIVE_MODELS.set(len(models))
    MODEL_NAMES.clear()
    for name in models:
        MODEL_NAMES.labels(model_name=name).set(1)


@app.get("/models")
def get_models():
    return models


@app.post("/register")
def register_model(model_name: str, host: str, port: int):
    models[model_name] = {"host": host, "port": port, "last_ping": time.time()}
    save_registry()
    update_metrics()
    return {"message": f"Model {model_name} registered successfully."}


@app.post("/unregister")
def unregister_model(model_name: str):
    if model_name in models:
        del models[model_name]
        save_registry()
        update_metrics()
        return {"message": f"Model {model_name} removed from registry."}
    raise HTTPException(status_code=404, detail="Model not found.")


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


def health_check():
    while True:
        time.sleep(10)
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
        update_metrics()


def queue_monitor():
    while True:
        fetch_queue_sizes()
        time.sleep(10)


threading.Thread(target=health_check, daemon=True).start()
threading.Thread(target=queue_monitor, daemon=True).start()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=9000)
