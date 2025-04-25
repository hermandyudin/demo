import asyncio
import atexit
import json
import socket
from abc import ABC, abstractmethod

import redis.asyncio as aioredis
import requests
from aio_pika import connect_robust, IncomingMessage
from fastapi import FastAPI, Request, Response
from google.protobuf.descriptor import Descriptor

import models_pb2


class BaseModel(ABC):
    def __init__(self, config_path: str, model_name: str, port: int):
        self.config = self._load_config(config_path)
        self.model_name = model_name
        self.port = port
        self.host = self._get_host_ip()

        self.app = FastAPI(lifespan=self.lifespan)
        self.redis = None
        self.queue_task = None

        self._setup_routes()
        self._register_with_registry()

        atexit.register(self._unregister_from_registry)

    # -------------------- Setup & Lifecycle --------------------
    def _setup_routes(self):
        self.app.get("/ping")(self._ping)
        self.app.post("/task")(self._handle_task)
        self.app.get("/schema")(self._get_schema)

    async def lifespan(self, app: FastAPI):
        await self._connect_redis()
        self.queue_task = asyncio.create_task(self._listen_to_rabbitmq())
        yield
        await self._shutdown()

    async def _shutdown(self):
        if self.queue_task:
            self.queue_task.cancel()
            try:
                await self.queue_task
            except asyncio.CancelledError:
                print("[*] RabbitMQ listener stopped.")
        if self.redis:
            await self.redis.close()
            print("[*] Redis connection closed.")

    # -------------------- HTTP Endpoints --------------------
    def _ping(self):
        return {"status": "ok"}

    async def _handle_task(self, request: Request):
        try:
            body = await request.body()
            result = await self.process_request(body)
            return Response(content=result.SerializeToString(), media_type="application/protobuf")
        except Exception as e:
            return Response(content=f"ProtoBuf decoding error: {str(e)}", status_code=400)

    async def _get_schema(self):
        input_desc = self.get_request_format()
        output_desc = self.get_response_format()

        request_example = self._fill_defaults_from_descriptor(input_desc)
        response_example = self._fill_defaults_from_descriptor(output_desc)

        return {
            "request": json.dumps(request_example, indent=2),
            "response": json.dumps(response_example, indent=2)
        }

    # -------------------- Redis & RabbitMQ --------------------
    async def _connect_redis(self):
        print("[*] Connecting to Redis...")
        self.redis = await aioredis.from_url(
            f"redis://{self.config['redis']['host']}:{self.config['redis']['port']}"
        )
        print("[*] Redis connected.")

    async def _listen_to_rabbitmq(self):
        print("[*] Connecting to RabbitMQ...")
        rabbitmq_host = self.config["rabbitmq"]["host"]
        connection = await connect_robust(f"amqp://guest:guest@{rabbitmq_host}/")
        channel = await connection.channel()
        queue = await channel.declare_queue(self.model_name)

        print(f"[*] Listening to queue: {self.model_name}")
        async for message in queue:
            await self._handle_message(message)

    async def _handle_message(self, message: IncomingMessage):
        async with message.process():
            print(f"[*] Processing task for model: {self.model_name}")
            task = models_pb2.Task()
            task.ParseFromString(message.body)
            print(f"Task ID: {task.task_id}")

            result = await self.process_request(task.request)
            await self.redis.set(task.task_id, result.SerializeToString())
            print(f"[*] Stored result in Redis with key: {task.task_id}")

    # -------------------- Registry --------------------
    def _register_with_registry(self):
        host = self.config["model_registry"]["host"]
        port = self.config["model_registry"]["port"]
        try:
            response = requests.post(
                f"http://{host}:{port}/register",
                params={"model_name": self.model_name, "host": self.host, "port": self.port}
            )
            print(f"[*] Registered with registry: {response.json()}")
        except requests.RequestException as e:
            print(f"[!] Failed to register: {e}")

    def _unregister_from_registry(self):
        host = self.config["model_registry"]["host"]
        port = self.config["model_registry"]["port"]
        try:
            response = requests.post(
                f"http://{host}:{port}/unregister",
                params={"model_name": self.model_name}
            )
            print(f"[*] Unregistered from registry: {response.json()}")
        except requests.ConnectionError:
            print("[!] Registry unavailable, will unregister later.")
        except requests.RequestException as e:
            print(f"[!] Unregister failed: {e}")

    # -------------------- Utils --------------------
    def _load_config(self, file_path: str):
        with open(file_path, "r") as f:
            return json.load(f)

    def _get_host_ip(self):
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "127.0.0.1"

    def _fill_defaults_from_descriptor(self, descriptor: Descriptor):
        result = {}
        for field in descriptor.fields:
            if field.label == field.LABEL_REPEATED:
                result[field.name] = [
                    self._fill_defaults_from_descriptor(field.message_type)
                ] if field.message_type else [self._get_default_value(field)]
            elif field.message_type:
                result[field.name] = self._fill_defaults_from_descriptor(field.message_type)
            else:
                result[field.name] = self._get_default_value(field)
        return result

    def _get_default_value(self, field):
        if field.cpp_type == field.CPPTYPE_STRING:
            return ""
        if field.cpp_type in (field.CPPTYPE_INT32, field.CPPTYPE_INT64):
            return 0
        if field.cpp_type == field.CPPTYPE_BOOL:
            return False
        if field.cpp_type in (field.CPPTYPE_FLOAT, field.CPPTYPE_DOUBLE):
            return 0.0
        return None

    # -------------------- Abstract Methods --------------------
    @abstractmethod
    async def process_request(self, body):
        pass

    @abstractmethod
    def get_request_format(self):
        pass

    @abstractmethod
    def get_response_format(self):
        pass
