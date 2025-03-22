# import asyncio
# import json
# import uuid
#
# import uvicorn
# from fastapi import FastAPI, HTTPException, Request, Depends
# from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
# from typing import Dict, Any
# import jwt
# import aio_pika
# import redis.asyncio as aioredis
# import requests
#
# # Load Configuration
# with open("config.json", "r") as f:
#     config = json.load(f)
#
# # JWT Secret Key
# SECRET_KEY = "ee4da053eef85264631f4d07e3b565f3fd47cc84b18016044e919ff2aec9f3ee4a0814d4768a14313780a7e0d3a62567ac19a3c5e1f7042e0ed378f4801e9a179d89d187a8391dda6c6ab1a5a55058ed2704f601b2e4613bbeb9f24269a8d366412d9e7ab0917ccf4a858fdec64b49683b134376487c94552131b8452f47a07f0591badf3a2ea1391c107f3aba5d583b6884f9978ca413ecf7366b04305f4909999e24cab024d29e4a1b6eb4ddfc78b5ca9f843b193101406b07798a2403ac4023008ab415be79f86beda37ad14840af39a49c4bf7afee76344753f2fc4ecc4613bc2dc4b35cb7f762dd1074cc1214bcf392db372c1a8ded8728fee8d83deae5"
# ALGORITHM = "HS256"
#
# # FastAPI app setup
# app = FastAPI()
# security = HTTPBearer()
#
# # Redis connection
# redis = None
#
#
# @app.on_event("startup")
# async def startup():
#     global redis
#     redis = await aioredis.from_url(
#         f"redis://{config['redis']['host']}:{config['redis']['port']}"
#     )
#     print("[*] Redis connected.")
#
#
# @app.on_event("shutdown")
# async def shutdown():
#     if redis:
#         await redis.close()
#
#
# # -------------------------------
# # JWT Utility Functions
# # -------------------------------
# def create_jwt(user_id: str) -> str:
#     payload = {"user_id": user_id}
#     token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
#     return token
#
#
# def decode_jwt(token: str) -> str:
#     try:
#         payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
#         return payload["user_id"]
#     except jwt.ExpiredSignatureError:
#         raise HTTPException(status_code=401, detail="Token expired")
#     except jwt.InvalidTokenError:
#         raise HTTPException(status_code=401, detail="Invalid token")
#
#
# # -------------------------------
# # 1. Get Active Models
# # -------------------------------
# @app.get("/models")
# async def get_models():
#     registry_host = config["model_registry"]["host"]
#     registry_port = config["model_registry"]["port"]
#     response = requests.get(f"http://{registry_host}:{registry_port}/models")
#     return response.json()
#
#
# # -------------------------------
# # 2. Get Model Schema
# # -------------------------------
# @app.get("/schema/{model_name}")
# async def get_schema(model_name: str):
#     models = await get_models()
#     if model_name not in models:
#         raise HTTPException(status_code=404, detail="Model not found")
#
#     host = models[model_name]["host"]
#     port = models[model_name]["port"]
#
#     try:
#         response = requests.get(f"http://{host}:{port}/schema")
#         return response.json()
#     except requests.exceptions.RequestException:
#         raise HTTPException(status_code=500, detail="Failed to get schema")


# # -------------------------------
# # 3. Send Task to Model
# # -------------------------------
# @app.post("/task/{model_name}")
# async def send_task(model_name: str, request: Request, token: HTTPAuthorizationCredentials = Depends(security)):
#     user_id = decode_jwt(token.credentials)
#
#     models = await get_models()
#     if model_name not in models:
#         raise HTTPException(status_code=404, detail="Model not found")
#
#     task_id = str(uuid.uuid4())
#     body = await request.body()
#
#     task = {
#         "task_id": task_id,
#         "user_id": user_id,
#         "request": body
#     }
#
#     # Send task to RabbitMQ
#     rabbitmq_host = config["rabbitmq"]["host"]
#     connection = await aio_pika.connect_robust(f"amqp://guest:guest@{rabbitmq_host}/")
#     channel = await connection.channel()
#
#     await channel.default_exchange.publish(
#         aio_pika.Message(body=json.dumps(task).encode()),
#         routing_key=model_name
#     )
#
#     await connection.close()
#
#     # Store task status in Redis
#     await redis.set(f"task:{task_id}", json.dumps({"status": "pending", "user_id": user_id}))
#
#     return {"task_id": task_id}
#
#
# # -------------------------------
# # 4. Get Task Status
# # -------------------------------
# @app.get("/task/{task_id}")
# async def get_task(task_id: str, token: HTTPAuthorizationCredentials = Depends(security)):
#     user_id = decode_jwt(token.credentials)
#
#     task = await redis.get(f"task:{task_id}")
#     if not task:
#         raise HTTPException(status_code=404, detail="Task not found")
#
#     task_data = json.loads(task)
#
#     if task_data["user_id"] != user_id:
#         raise HTTPException(status_code=403, detail="Unauthorized")
#
#     return task_data


# # -------------------------------
# # 5. Generate Token for Testing
# # -------------------------------
# @app.post("/token")
# async def generate_token(user_id: str):
#     token = create_jwt(user_id)
#     return {"token": token}

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.openapi.utils import get_openapi
import requests
import os

REGISTRY_HOST = os.getenv('REGISTRY_HOST', 'localhost')
REGISTRY_PORT = os.getenv('REGISTRY_PORT', 9000)

app = FastAPI()

# --- Get Active Models ---
def get_active_models():
    try:
        response = requests.get(f"http://{REGISTRY_HOST}:{REGISTRY_PORT}/models")
        return response.json()
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- Fetch Schema from Models ---
def fetch_schemas():
    schemas = {}
    models = get_active_models()
    for model_name, model_info in models.items():
        try:
            response = requests.get(f"http://{model_info['host']}:{model_info['port']}/schema")
            schemas[model_name] = response.json()
        except requests.exceptions.RequestException as e:
            print(f"Failed to fetch schema for {model_name}: {e}")
    return schemas

# --- Convert Proto Types to OpenAPI Types ---
PROTO_TO_OPENAPI = {
    1: "number",    # TYPE_DOUBLE
    2: "number",    # TYPE_FLOAT
    3: "integer",   # TYPE_INT64
    4: "integer",   # TYPE_UINT64
    5: "integer",   # TYPE_INT32
    6: "integer",   # TYPE_FIXED64
    7: "integer",   # TYPE_FIXED32
    8: "boolean",   # TYPE_BOOL
    9: "string",    # TYPE_STRING
    12: "string",   # TYPE_BYTES
}

def convert_proto_to_openapi(proto_type):
    return PROTO_TO_OPENAPI.get(proto_type, "string")

# --- Build Dynamic OpenAPI Schema ---
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title="Dynamic Model API",
        version="1.0.0",
        description="Dynamically generated API for registered models",
        routes=app.routes,
    )

    # Prepare space for dynamic schemas
    if "components" not in openapi_schema:
        openapi_schema["components"] = {"schemas": {}}

    schemas = fetch_schemas()

    for model_name, schema in schemas.items():
        # --- Define request schema ---
        request_properties = {
            field: {"type": convert_proto_to_openapi(field_type)}
            for field, field_type in schema["request"].items()
        }

        response_properties = {
            field: {"type": convert_proto_to_openapi(field_type)}
            for field, field_type in schema["response"].items()
        }

        # Register request schema
        openapi_schema["components"]["schemas"][f"{model_name}Request"] = {
            "type": "object",
            "properties": request_properties
        }

        # Register response schema
        openapi_schema["components"]["schemas"][f"{model_name}Response"] = {
            "type": "object",
            "properties": response_properties
        }

        # --- Add route for model ---
        openapi_schema["paths"][f"/{model_name}/request"] = {
            "post": {
                "summary": f"Send request to {model_name}",
                "description": f"Send a request to {model_name} and get a response",
                "requestBody": {
                    "content": {
                        "application/json": {
                            "schema": {"$ref": f"#/components/schemas/{model_name}Request"}
                        }
                    }
                },
                "responses": {
                    "200": {
                        "description": "Successful response",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": f"#/components/schemas/{model_name}Response"}
                            }
                        }
                    }
                }
            }
        }

    app.openapi_schema = openapi_schema
    return app.openapi_schema

# Assign the custom OpenAPI function to FastAPI
app.openapi = custom_openapi

# --- Get Active Models Endpoint ---
@app.get("/models")
def get_models():
    return get_active_models()


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8002)