from fastapi import FastAPI, HTTPException
import json
import os
import requests
import time
import threading

REGISTRY_FILE = "models_registry.json"

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


@app.get("/models")
def get_models():
    """Return a list of active models"""
    return models


@app.post("/register")
def register_model(model_name: str, host: str, port: int):
    """Register a new model in the registry"""
    models[model_name] = {"host": host, "port": port, "last_ping": time.time()}
    save_registry()
    return {"message": f"Model {model_name} registered successfully."}


@app.post("/unregister")
def unregister_model(model_name: str):
    """Unregister a model"""
    if model_name in models:
        del models[model_name]
        save_registry()
        return {"message": f"Model {model_name} removed from registry."}
    raise HTTPException(status_code=404, detail="Model not found.")


# Health check (removes dead models)
def health_check():
    while True:
        time.sleep(10)  # Run every 10 seconds
        for model_name in list(models.keys()):
            host, port = models[model_name]["host"], models[model_name]["port"]
            try:
                response = requests.get(f"http://{host}:{port}/ping", timeout=3)
                if response.status_code == 200:
                    models[model_name]["last_ping"] = time.time()
                else:
                    del models[model_name]
            except requests.exceptions.RequestException:
                del models[model_name]
        save_registry()


# Start health check thread
threading.Thread(target=health_check, daemon=True).start()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=9000)
