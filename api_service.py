# api_component.py

import asyncio
import uuid
import requests
import redis.asyncio as aioredis
from fastapi import FastAPI, HTTPException, Request
from fastapi.openapi.utils import get_openapi
from contextlib import asynccontextmanager
from aio_pika import connect_robust, Message
from openapi_utils import *
import models_pb2

# Load configuration
with open("config.json") as f:
    config = json.load(f)


class ModelAPIService:
    def __init__(self):
        self.app = FastAPI(lifespan=self.lifespan)
        self.redis = None
        self.models = {}
        self.descriptors_cache = {}
        self.refresh_interval = config.get("refresh_interval", 60)
        self.rabbitmq_channel = None
        self._setup_routes()

    def _setup_routes(self):
        self.app.get("/models")(self.list_models)
        self.app.post("/models/{model_name}/tasks")(self.submit_task)
        self.app.get("/models/{model_name}/result")(self.get_task_result)
        self.app.openapi = self.custom_openapi

    @asynccontextmanager
    async def lifespan(self, app: FastAPI):
        await self.connect_redis()
        await self.connect_rabbitmq()
        await self.discover_models()
        asyncio.create_task(self.refresh_models_loop())
        yield
        await self.close_rabbitmq()
        await self.close_redis()

    async def connect_redis(self):
        self.redis = await aioredis.from_url(
            f"redis://{config['redis']['host']}:{config['redis']['port']}"
        )

    async def connect_rabbitmq(self):
        rabbitmq_host = config['rabbitmq']['host']
        connection = await connect_robust(f"amqp://guest:guest@{rabbitmq_host}/")
        self.rabbitmq_channel = await connection.channel()

    async def close_rabbitmq(self):
        if self.rabbitmq_channel:
            await self.rabbitmq_channel.close()

    async def close_redis(self):
        if self.redis:
            await self.redis.close()

    async def refresh_models_loop(self):
        """Background task to refresh model list and OpenAPI schema periodically."""
        while True:
            await self.discover_models()
            self.descriptors_cache = {}
            self.app.openapi_schema = None
            await asyncio.sleep(self.refresh_interval)

    async def discover_models(self):
        """Fetch available models from the registry service."""
        registry_url = f"http://{config['model_registry']['host']}:{config['model_registry']['port']}/models"
        try:
            response = requests.get(registry_url)
            self.models = response.json()
        except requests.RequestException as e:
            print(f"Failed to fetch models from registry: {e}")
            self.models = {}

    # ======================
    #        API ROUTES
    # ======================

    async def list_models(self):
        return {"models": list(self.models.keys())}

    async def submit_task(self, model_name: str, request: Request):
        """Accept JSON input, convert to Protobuf, publish to RabbitMQ"""
        if model_name not in self.models:
            raise HTTPException(status_code=404, detail="Model not found")

        # Parse JSON request
        json_body = await request.json()

        # Get descriptor
        descriptor = self.get_descriptor(model_name, "request")
        message = json_to_protobuf(descriptor, json_body)

        # Prepare Task
        task = models_pb2.Task()
        task.task_id = str(uuid.uuid4())
        task.request = message.SerializeToString()

        # Publish to RabbitMQ
        queue_name = model_name
        await self.rabbitmq_channel.default_exchange.publish(
            Message(body=task.SerializeToString()),
            routing_key=queue_name
        )

        return {"task_id": task.task_id}

    async def get_task_result(self, model_name: str, task_id: str):
        """Fetch result from Redis, decode Proto, return as JSON"""
        full_task_id = task_id

        print(f"{full_task_id}\n")

        data = await self.redis.get(full_task_id)
        if not data:
            return {"task_id": task_id, "status": "not_found"}

        descriptor = self.get_descriptor(model_name, "response")
        message = bytes_to_protobuf(descriptor, data)
        return {"task_id": task_id, "status": "completed", "result": protobuf_to_dict(message)}

    # ======================
    #     OPENAPI HELPERS
    # ======================

    def get_active_models(self):
        try:
            response = requests.get(
                f"http://{config['model_registry']['host']}:{config['model_registry']['port']}/models")
            return response.json()
        except requests.exceptions.RequestException as e:
            raise HTTPException(status_code=500, detail=str(e))

    def fetch_descriptors(self):
        """Fetch descriptors and build default-filled JSONs."""
        if self.descriptors_cache:
            return self.descriptors_cache

        descriptors = {}
        models = self.get_active_models()
        for model_name, model_info in models.items():
            try:
                req_desc_resp = requests.get(f"http://{model_info['host']}:{model_info['port']}/get_request_format")
                res_desc_resp = requests.get(f"http://{model_info['host']}:{model_info['port']}/get_response_format")

                req_desc = parse_descriptor(req_desc_resp.content)
                res_desc = parse_descriptor(res_desc_resp.content)

                descriptors[model_name] = {
                    "request": req_desc,
                    "response": res_desc
                }
            except requests.exceptions.RequestException as e:
                print(f"Failed to fetch schema for {model_name}: {e}")

        self.descriptors_cache = descriptors
        return descriptors

    def get_descriptor(self, model_name, kind):
        """Helper to get request or response descriptor."""
        descriptors = self.fetch_descriptors()
        if model_name not in descriptors:
            raise HTTPException(status_code=404, detail=f"Descriptor for model {model_name} not found.")
        return descriptors[model_name][kind]

    def custom_openapi(self):
        if self.app.openapi_schema:
            return self.app.openapi_schema

        openapi_schema = get_openapi(
            title="Model API Gateway",
            version="1.0.0",
            routes=self.app.routes,
        )

        openapi_schema["components"] = {"schemas": {}}
        descriptors_data = self.fetch_descriptors()

        for model_name, descriptors in descriptors_data.items():
            req_data = fill_defaults_from_descriptor(descriptors.get("request"))
            res_data = fill_defaults_from_descriptor(descriptors.get("response"))

            request_schema = generate_openapi_schema(req_data)
            response_schema = generate_openapi_schema(res_data)

            req_name = f"{model_name}_Request"
            res_name = f"{model_name}_Response"

            # Register in components
            openapi_schema["components"]["schemas"][req_name] = request_schema
            openapi_schema["components"]["schemas"][res_name] = response_schema

            # Register in paths
            paths = generate_model_paths(
                model_name,
                request_schema_ref=f"#/components/schemas/{req_name}",
                response_schema_ref=f"#/components/schemas/{res_name}",
            )
            openapi_schema["paths"].update(paths)

        self.app.openapi_schema = openapi_schema
        return openapi_schema


# Application entry point
if __name__ == "__main__":
    import uvicorn

    api_service = ModelAPIService()
    uvicorn.run(api_service.app, host="0.0.0.0", port=8002)
