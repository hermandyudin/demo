import json
import asyncio
from fastapi import FastAPI, HTTPException, Depends, Request, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.openapi.utils import get_openapi
from google.protobuf.descriptor import Descriptor
from typing import Dict, Any, List, Optional
import aio_pika
import redis.asyncio as aioredis
import uuid
import secrets
import requests
from contextlib import asynccontextmanager

# Configuration
with open('config.json') as f:
    config = json.load(f)

# Security setup
security = HTTPBasic()
active_users = {}


class ModelAPIService:
    def __init__(self):
        self.app = FastAPI(lifespan=self.lifespan)
        self.redis = None
        self.models = {}
        self._setup_routes()

    def _setup_routes(self):
        self.app.get("/models")(self.list_models)
        self.app.get("/tasks/{task_id}")(self.get_task_status)
        self.app.openapi = self.custom_openapi

    @asynccontextmanager
    async def lifespan(self, app: FastAPI):
        # Startup
        await self.connect_redis()
        await self.discover_models()
        yield
        # Shutdown
        await self.close_redis()

    async def connect_redis(self):
        self.redis = await aioredis.from_url(
            f"redis://{config['redis']['host']}:{config['redis']['port']}"
        )

    async def close_redis(self):
        if self.redis:
            await self.redis.close()

    async def discover_models(self):
        """Fetch available models from registry"""
        registry_url = f"http://{config['model_registry']['host']}:{config['model_registry']['port']}/models"
        try:
            response = requests.get(registry_url)
            self.models = response.json()
        except requests.RequestException as e:
            print(f"Failed to fetch models from registry: {e}")
            self.models = {}

    async def authenticate(self, credentials: HTTPBasicCredentials):
        # In a real implementation, validate against your user store
        token = secrets.token_hex(16)
        active_users[token] = credentials.username
        return token

    # Helper methods for Protobuf to OpenAPI conversion
    def descriptor_to_swagger(self, descriptor: Descriptor) -> Dict[str, Any]:
        schema = {
            "type": "object",
            "properties": {},
            "required": []
        }

        for field in descriptor.fields:
            field_schema = self._field_to_swagger(field)
            schema["properties"][field.name] = field_schema
            if field.label == field.LABEL_REQUIRED:
                schema["required"].append(field.name)

        return schema

    def _field_to_swagger(self, field) -> Dict[str, Any]:
        type_map = {
            1: {"type": "number", "format": "double"},
            5: {"type": "integer", "format": "int32"},
            8: {"type": "string"},
            9: {"$ref": f"#/components/schemas/{field.message_type.name}"},
            10: {"type": "string", "enum": [v.name for v in field.enum_type.values]},
        }

        if field.label == field.LABEL_REPEATED:
            return {"type": "array", "items": type_map.get(field.type, {"type": "string"})}

        return type_map.get(field.type, {"type": "string"})

    # API Endpoints
    async def list_models(self):
        return {"models": list(self.models.keys())}

    async def get_task_status(self, task_id: str, credentials: HTTPBasicCredentials = Depends(security)):
        token = await self.authenticate(credentials)
        user = active_users[token]

        result = await self.redis.get(f"{user}:{task_id}")
        if not result:
            return {"task_id": task_id, "status": "not_found"}

        return {"task_id": task_id, "status": "completed", "result": result.decode()}

    def get_active_models(self):
        try:
            response = requests.get(
                f"http://{config['model_registry']['host']}:{config['model_registry']['port']}/models")
            return response.json()
        except requests.exceptions.RequestException as e:
            raise HTTPException(status_code=500, detail=str(e))

    def fetch_schemas(self):
        schemas = {}
        models = self.get_active_models()
        for model_name, model_info in models.items():
            try:
                response = requests.get(f"http://{model_info['host']}:{model_info['port']}/schema")
                schemas[model_name] = response.json()
            except requests.exceptions.RequestException as e:
                print(f"Failed to fetch schema for {model_name}: {e}")
        return schemas

    def generate_openapi_schema(self, data):
        """
        Recursively converts a Python dictionary into an OpenAPI schema.
        """
        if isinstance(data, dict):
            properties = {key: self.generate_openapi_schema(value) for key, value in data.items()}
            return {"type": "object", "properties": properties}

        elif isinstance(data, list):
            return {
                "type": "array",
                "items": self.generate_openapi_schema(data[0]) if data else {"type": "string"}
            }

        elif isinstance(data, str):
            return {"type": "string"}

        elif isinstance(data, int):
            return {"type": "integer"}

        elif isinstance(data, float):
            return {"type": "number"}

        elif isinstance(data, bool):
            return {"type": "boolean"}

        else:
            return {"type": "string"}

    def custom_openapi(self):
        if self.app.openapi_schema:
            return self.app.openapi_schema

        openapi_schema = get_openapi(
            title="Model API Gateway",
            version="1.0.0",
            routes=self.app.routes,
        )

        openapi_schema["components"] = {"schemas": {}}
        schema = self.fetch_schemas()

        for model_name in self.models:
            # Generate and store request schema
            request_data = json.loads(schema[model_name]["request"])
            request_schema = self.generate_openapi_schema(request_data)
            request_schema_name = f"{model_name}_Request"
            openapi_schema["components"]["schemas"][request_schema_name] = request_schema

            # Generate and store response schema
            response_data = json.loads(schema[model_name]["response"])
            response_schema = self.generate_openapi_schema(response_data)
            response_schema_name = f"{model_name}_Response"
            openapi_schema["components"]["schemas"][response_schema_name] = response_schema

            # Add /tasks POST endpoint
            openapi_schema["paths"][f"/models/{model_name}/tasks"] = {
                "post": {
                    "summary": f"Submit task to {model_name}",
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "$ref": f"#/components/schemas/{request_schema_name}"
                                }
                            }
                        }
                    },
                    "responses": {
                        "200": {
                            "description": "Task submitted successfully",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "task_id": {"type": "integer"}
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }

            # Add /result GET endpoint
            openapi_schema["paths"][f"/models/{model_name}/result"] = {
                "get": {
                    "summary": f"Get task status from {model_name}",
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "task_id": {"type": "integer"}
                                    }
                                }
                            }
                        }
                    },
                    "responses": {
                        "200": {
                            "description": "Result of the task",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "status": {"type": "string"},
                                            "result": {
                                                "$ref": f"#/components/schemas/{response_schema_name}"
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }

        self.app.openapi_schema = openapi_schema
        return openapi_schema


# Application entry point
if __name__ == "__main__":
    import uvicorn

    api_service = ModelAPIService()
    uvicorn.run(api_service.app, host="0.0.0.0", port=8002)
