from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
import json
import os
import requests
import time
import threading
from prometheus_client import Gauge, generate_latest, CONTENT_TYPE_LATEST
from utils.rabbitmq_monitoring import fetch_queue_sizes

import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger()

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
        json.dump(models, f, indent=2)


def update_metrics():
    ACTIVE_MODELS.set(len(models))
    MODEL_NAMES.clear()
    for name in models:
        MODEL_NAMES.labels(model_name=name).set(1)


@app.get("/models")
def get_models():
    return models


@app.post("/register")
def register_model(model_name: str, host: str, port: int, input_model: str, output_model: str):
    instance = {"host": host, "port": port, "last_ping": time.time()}

    if model_name not in models:
        models[model_name] = {"instances": [instance], "input_model": input_model, "output_model": output_model}
    else:
        if models[model_name]["input_model"] != input_model or models[model_name]["output_model"] != output_model:
            raise ValueError(
                f"Model '{model_name}' is already registered with a different input/output schema.\n"
                f"Existing input_model: {models[model_name]['input_model']}, new: {input_model}\n"
                f"Existing output hash: {models[model_name]['output_model']}, new: {output_model}"
            )
        instances = models[model_name]["instances"]
        # Avoid duplicates
        if not any(inst["host"] == host and inst["port"] == port for inst in instances):
            instances.append(instance)

    logger.info(
        f"Registered new instance for {model_name}. Host {host}, port ${port}. Now it has {len(models[model_name]['instances'])} instances")
    save_registry()
    update_metrics()
    return {"message": f"Model {model_name} registered with instance {host}:{port}"}


@app.post("/unregister")
def unregister_model(model_name: str, host: str, port: int):
    if model_name not in models:
        raise HTTPException(status_code=404, detail="Model not found.")

    instances = models[model_name]["instances"]
    filtered = [inst for inst in instances if not (inst["host"] == host and inst["port"] == port)]
    if filtered:
        models[model_name]["instances"] = filtered
    else:
        del models[model_name]

    logger.info(
        f"Unregistered instance for {model_name}. Host {host}, port {port}. Now it has {len(models[model_name]['instances'])} instances")
    save_registry()
    update_metrics()
    return {"message": f"Unregistered instance {host}:{port} from model {model_name}"}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


def health_check():
    while True:
        time.sleep(10)
        models_changed = False

        for model_name in list(models.keys()):
            active_instances = []
            for inst in models[model_name]["instances"]:
                url = f"http://{inst['host']}:{inst['port']}/ping"
                logger.info(f"Pinging instance of {model_name}, host: {inst['host']}, port: {inst['port']}")
                try:
                    response = requests.get(url, timeout=3)
                    if response.status_code == 200:
                        inst["last_ping"] = time.time()
                        active_instances.append(inst)
                except requests.RequestException:
                    pass  # Instance is considered down

            if active_instances:
                models[model_name]["instances"] = active_instances
            else:
                del models[model_name]
            models_changed = True

        if models_changed:
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
