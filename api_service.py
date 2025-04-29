import asyncio
import uuid
import requests
import redis.asyncio as aioredis
from fastapi import FastAPI, HTTPException, Request, Security
from fastapi.openapi.utils import get_openapi
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from jose import jwt, JWTError
from contextlib import asynccontextmanager
from aio_pika import connect_robust, Message
from openapi_utils import *
import models_pb2
from passlib.context import CryptContext
import os
import json

# Load config
with open("config.json") as f:
    config = json.load(f)

# JWT and Security
SECRET_KEY = config["jwt"]["secret_key"]
ALGORITHM = config["jwt"].get("algorithm", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = 60
security = HTTPBearer()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
USER_FILE = "users.json"


# =====================================
#              AUTH HELPERS
# =====================================

class User(BaseModel):
    username: str
    password: str


def load_users():
    if not os.path.exists(USER_FILE):
        return {}
    with open(USER_FILE, "r") as f:
        return json.load(f)


def save_users(users):
    with open(USER_FILE, "w") as f:
        json.dump(users, f, indent=2)


def get_user(username: str):
    users = load_users()
    return users.get(username)


def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict):
    from datetime import datetime, timedelta
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(credentials: HTTPAuthorizationCredentials = Security(security)):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token: missing subject")
        return user_id
    except JWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")


# =====================================
#             MAIN SERVICE
# =====================================

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
        self.app.post("/register")(self.register_user)
        self.app.post("/login")(self.login_user)
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
        while True:
            await self.discover_models()
            self.descriptors_cache = {}
            self.app.openapi_schema = None
            await asyncio.sleep(self.refresh_interval)

    async def discover_models(self):
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

    async def submit_task(self, model_name: str, request: Request, user_id: str = Security(get_current_user)):
        if model_name not in self.models:
            raise HTTPException(status_code=404, detail="Model not found")

        json_body = await request.json()
        descriptor = self.get_descriptor(model_name, "request")
        message = json_to_protobuf(descriptor, json_body)

        task = models_pb2.Task()
        task_uid = uuid.uuid4()
        task.task_id = f"{user_id}:{task_uid}"
        task.request = message.SerializeToString()

        await self.rabbitmq_channel.default_exchange.publish(
            Message(body=task.SerializeToString()),
            routing_key=model_name
        )

        return {"task_id": task_uid}

    async def get_task_result(self, model_name: str, task_id: str, user_id: str = Security(get_current_user)):
        full_task_id = f"{user_id}:{task_id}"
        data = await self.redis.get(full_task_id)
        if not data:
            return {"task_id": task_id, "status": "not_found"}

        descriptor = self.get_descriptor(model_name, "response")
        message = bytes_to_protobuf(descriptor, data)
        return {"task_id": task_id, "status": "completed", "result": protobuf_to_dict(message)}

    # ======================
    #     AUTH ROUTES
    # ======================

    async def register_user(self, user: User):
        users = load_users()
        if user.username in users:
            raise HTTPException(status_code=400, detail="Username already exists")
        hashed_pw = pwd_context.hash(user.password)
        users[user.username] = {"hashed_password": hashed_pw}
        save_users(users)
        return {"message": "User registered"}

    async def login_user(self, user: User):
        users = load_users()
        user_data = users.get(user.username)
        if not user_data or not verify_password(user.password, user_data["hashed_password"]):
            raise HTTPException(status_code=400, detail="Incorrect username or password")
        token = create_access_token(data={"sub": user.username})
        return {"access_token": token, "token_type": "bearer"}

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

        openapi_schema["components"] = openapi_schema.get("components", {})
        openapi_schema["components"]["securitySchemes"] = {
            "BearerAuth": {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "JWT"
            }
        }

        for path_item in openapi_schema["paths"].values():
            for operation in path_item.values():
                operation["security"] = [{"BearerAuth": []}]

        descriptors_data = self.fetch_descriptors()
        openapi_schema["components"]["schemas"] = {}

        for model_name, descriptors in descriptors_data.items():
            req_data = fill_defaults_from_descriptor(descriptors["request"])
            res_data = fill_defaults_from_descriptor(descriptors["response"])

            request_schema = generate_openapi_schema(req_data)
            response_schema = generate_openapi_schema(res_data)

            req_name = f"{model_name}_Request"
            res_name = f"{model_name}_Response"

            openapi_schema["components"]["schemas"][req_name] = request_schema
            openapi_schema["components"]["schemas"][res_name] = response_schema

            paths = generate_model_paths(
                model_name,
                request_schema_ref=f"#/components/schemas/{req_name}",
                response_schema_ref=f"#/components/schemas/{res_name}",
            )
            openapi_schema["paths"].update(paths)

        inject_static_schemas(openapi_schema)

        self.app.openapi_schema = openapi_schema
        return self.app.openapi_schema


# Application entry point
if __name__ == "__main__":
    import uvicorn

    api_service = ModelAPIService()
    uvicorn.run(api_service.app, host="0.0.0.0", port=8002)
