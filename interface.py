import asyncio
from abc import ABC, abstractmethod
from typing import Any, Dict

from fastapi import FastAPI, Request, Response
import requests
import json
import atexit
import socket
from aio_pika import connect_robust, IncomingMessage
import redis.asyncio as aioredis
from google.protobuf.descriptor import Descriptor

import models_pb2


# Load Configuration
def load_config(file_name):
    with open(file_name, "r") as f:
        return json.load(f)


# Get Host IP Address
def get_host_ip():
    try:
        return socket.gethostbyname(socket.gethostname())
    except Exception:
        return "127.0.0.1"


def descriptor_to_dict(descriptor: Descriptor) -> Dict[str, Any]:
    fields = {}
    for field in descriptor.fields:
        fields[field.name] = field.type
    return fields


class BaseModel(ABC):
    def __init__(self, config_file, model_name, port):
        self.config = load_config(config_file)
        self.model_name = model_name
        self.port = port
        self.host = get_host_ip()
        self.app = FastAPI(lifespan=self.lifespan)
        self.setup_routes()
        self.register_with_registry()
        self.queue_task = None
        self.redis = None

        # Unregister on exit
        atexit.register(self.unregister_from_registry)

    def setup_routes(self):
        self.app.get("/ping")(self.ping)
        self.app.post("/task")(self.handle_task)
        self.app.get("/schema")(self.get_schema)

    def ping(self):
        return {"status": "ok"}

    def register_with_registry(self):
        registry_host = self.config["model_registry"]["host"]
        registry_port = self.config["model_registry"]["port"]
        try:
            response = requests.post(
                f"http://{registry_host}:{registry_port}/register",
                params={"model_name": self.model_name, "host": self.host, "port": self.port}
            )
            print(response.json())
        except requests.exceptions.RequestException as e:
            print(f"Failed to register with Model Registry: {e}")

    def unregister_from_registry(self):
        registry_host = self.config["model_registry"]["host"]
        registry_port = self.config["model_registry"]["port"]
        try:
            response = requests.post(
                f"http://{registry_host}:{registry_port}/unregister",
                params={"model_name": self.model_name}
            )
            print(response.json())
        except requests.exceptions.ConnectionError:
            print("Warning: Model Registry is unavailable. The model will be unregistered when the registry is back online.")
        except requests.exceptions.RequestException as e:
            print(f"Failed to unregister from Model Registry due to an unexpected error: {e}")

    async def lifespan(self, app):
        # Start Redis connection
        print("[*] Connecting to Redis...")
        self.redis = await aioredis.from_url(
            f"redis://{self.config['redis']['host']}:{self.config['redis']['port']}"
        )
        print("[*] Redis connected.")

        # Start RabbitMQ connection
        print("[*] Starting RabbitMQ listener...")
        self.queue_task = asyncio.create_task(self.listen_to_queue())
        yield

        # Stop RabbitMQ listener and Redis connection on shutdown
        print("[*] Stopping RabbitMQ listener...")
        if self.queue_task:
            self.queue_task.cancel()
            try:
                await self.queue_task
            except asyncio.CancelledError:
                print("[*] RabbitMQ listener stopped.")

        print("[*] Closing Redis connection...")
        if self.redis:
            await self.redis.close()

    async def handle_task(self, request: Request):
        body = await request.body()
        try:
            response_object = await self.process_request(body)
        except Exception as e:
            return Response(content=f"ProtoBuf decoding error: {str(e)}", status_code=400)

        return Response(content=response_object.SerializeToString(), media_type="application/protobuf")

    async def listen_to_queue(self):
        rabbitmq_host = self.config["rabbitmq"]["host"]
        queue_name = self.model_name

        connection = await connect_robust(f"amqp://guest:guest@{rabbitmq_host}/")
        channel = await connection.channel()

        # Declare queue
        queue = await channel.declare_queue(queue_name)

        print(f"[*] Listening to RabbitMQ queue: {queue_name}")

        async for message in queue:
            await self.handle_message(message)

    async def handle_message(self, message: IncomingMessage):
        async with message.process():
            print(f"Processing request for {self.model_name}")
            task = models_pb2.Task()
            task.ParseFromString(message.body)
            print(f"Task id: {task.task_id}")

            # Process request
            result = await self.process_request(task.request)

            # Store result in Redis using task_id as the key
            await self.redis.set(task.task_id, result.SerializeToString())

            print(f"Stored result in Redis with key: {task.task_id}")

    async def get_schema(self):
        request_descriptor = self.get_request_descriptor()
        response_descriptor = self.get_response_descriptor()

        return {
            "request": descriptor_to_dict(request_descriptor),
            "response": descriptor_to_dict(response_descriptor)
        }

    @abstractmethod
    async def process_request(self, body):
        pass

    @abstractmethod
    def get_request_descriptor(self) -> Descriptor:
        pass

    @abstractmethod
    def get_response_descriptor(self) -> Descriptor:
        pass