import asyncio
import atexit
import base64
import json
import socket
from abc import ABC, abstractmethod

import redis.asyncio as aioredis
import requests
from aio_pika import connect_robust, IncomingMessage
from fastapi import FastAPI, Request, Response
from google.protobuf import descriptor_pb2

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
        self.app.get("/get_request_format")(self._get_request_format)
        self.app.get("/get_response_format")(self._get_response_format)

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

    async def _get_request_format(self):
        descriptor = self.get_request_format()
        file_proto = descriptor_pb2.FileDescriptorProto()
        descriptor.file.CopyToProto(file_proto)
        descriptor_bytes = file_proto.SerializeToString()
        descriptor_base64 = base64.b64encode(descriptor_bytes).decode('utf-8')
        response_data = {
            'message_name': descriptor.full_name,
            'descriptor_bytes': descriptor_base64
        }
        return Response(json.dumps(response_data), media_type='application/json')

    async def _get_response_format(self):
        descriptor = self.get_response_format()
        file_proto = descriptor_pb2.FileDescriptorProto()
        descriptor.file.CopyToProto(file_proto)
        descriptor_bytes = file_proto.SerializeToString()
        descriptor_base64 = base64.b64encode(descriptor_bytes).decode('utf-8')
        response_data = {
            'message_name': descriptor.full_name,
            'descriptor_bytes': descriptor_base64
        }
        return Response(json.dumps(response_data), media_type='application/json')

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
