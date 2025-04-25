import json
import asyncio
import secrets
import requests
import redis.asyncio as aioredis
from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.openapi.utils import get_openapi
from contextlib import asynccontextmanager
from openapi_utils import generate_openapi_schema, generate_model_paths

# Load configuration
with open("config.json") as f:
    config = json.load(f)

# Security setup
security = HTTPBasic()
active_users = {}


class ModelAPIService:
    def __init__(self):
        self.app = FastAPI(lifespan=self.lifespan)
        self.redis = None
        self.models = {}
        self.schema_cache = {}
        self.refresh_interval = config.get("refresh_interval", 60)
        self._setup_routes()

    def _setup_routes(self):
        self.app.get("/models")(self.list_models)
        self.app.get("/tasks/{task_id}")(self.get_task_status)
        self.app.openapi = self.custom_openapi

    @asynccontextmanager
    async def lifespan(self, app: FastAPI):
        await self.connect_redis()
        await self.discover_models()
        asyncio.create_task(self.refresh_models_loop())
        yield
        await self.close_redis()

    async def connect_redis(self):
        self.redis = await aioredis.from_url(
            f"redis://{config['redis']['host']}:{config['redis']['port']}"
        )

    async def close_redis(self):
        if self.redis:
            await self.redis.close()

    async def refresh_models_loop(self):
        """Background task to refresh model list and OpenAPI schema periodically."""
        while True:
            await self.discover_models()
            self.schema_cache = {}
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

    async def authenticate(self, credentials: HTTPBasicCredentials):
        # In production, validate user from DB or external system
        token = secrets.token_hex(16)
        active_users[token] = credentials.username
        return token

    # =======================
    #        API ROUTES
    # =======================

    async def list_models(self):
        return {"models": list(self.models.keys())}

    async def get_task_status(self, task_id: str, credentials: HTTPBasicCredentials = Depends(security)):
        token = await self.authenticate(credentials)
        user = active_users[token]
        result = await self.redis.get(f"{user}:{task_id}")
        if not result:
            return {"task_id": task_id, "status": "not_found"}
        return {"task_id": task_id, "status": "completed", "result": result.decode()}

    # =======================
    #     OPENAPI HELPERS
    # =======================

    def get_active_models(self):
        try:
            response = requests.get(
                f"http://{config['model_registry']['host']}:{config['model_registry']['port']}/models")
            return response.json()
        except requests.exceptions.RequestException as e:
            raise HTTPException(status_code=500, detail=str(e))

    def fetch_schemas(self):
        """Fetch /schema from each model. Cached until next refresh."""
        if self.schema_cache:
            return self.schema_cache

        schemas = {}
        models = self.get_active_models()
        for model_name, model_info in models.items():
            try:
                response = requests.get(f"http://{model_info['host']}:{model_info['port']}/schema")
                schemas[model_name] = response.json()
            except requests.exceptions.RequestException as e:
                print(f"Failed to fetch schema for {model_name}: {e}")
        self.schema_cache = schemas
        return schemas

    def generate_openapi_schema(self, data):
        """Recursively generates an OpenAPI schema from a nested dict."""
        if isinstance(data, dict):
            return {
                "type": "object",
                "properties": {
                    key: self.generate_openapi_schema(value) for key, value in data.items()
                }
            }
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
        schema_data = self.fetch_schemas()

        for model_name, schema in schema_data.items():
            req_data = json.loads(schema.get("request", "{}"))
            res_data = json.loads(schema.get("response", "{}"))

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
