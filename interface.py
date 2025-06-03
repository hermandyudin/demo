import asyncio
import atexit
import base64
import json
import socket
from abc import ABC, abstractmethod
from typing import TypeVar, Generic, Type
import redis.asyncio as aioredis
import requests
import os
from aio_pika import connect_robust, IncomingMessage
import aio_pika
from fastapi import FastAPI, Request, Response
from google.protobuf import descriptor_pb2
from google.protobuf.message import Message

import models_pb2

import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger()

# -------------------- Type Variables --------------------
RequestType = TypeVar("RequestType", bound=Message)
ResponseType = TypeVar("ResponseType", bound=Message)


class BaseModel(ABC, Generic[RequestType, ResponseType]):
    request_cls: Type[RequestType]
    response_cls: Type[ResponseType]

    def __init__(self, model_name: str, port: int):
        self.config = self._load_config(os.environ.get("CONFIG_PATH", "config.json"))
        self.model_name = model_name
        self.port = port
        self.host = self._get_host_ip()

        self.app = FastAPI()
        self.redis = None

        self._setup_routes()
        self._register_with_registry()

        atexit.register(self._unregister_from_registry)

    # -------------------- Setup & Lifecycle --------------------
    def _setup_routes(self):
        self.app.get("/ping")(self._ping)
        self.app.post("/task")(self._handle_task)
        self.app.get("/get_request_format")(self._get_request_format)
        self.app.get("/get_response_format")(self._get_response_format)

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
        if self.redis is None:
            logger.info("[*] Connecting to Redis...")
            self.redis = await aioredis.from_url(
                f"redis://{self.config['redis']['host']}:{self.config['redis']['port']}"
            )
            logger.info("[*] Redis connected.")

    async def connect_rabbitmq(self):
        rabbitmq_host = self.config['rabbitmq']['host']
        retries = 10
        for i in range(retries):
            try:
                connection = await connect_robust(f"amqp://guest:guest@{rabbitmq_host}/")
                self.rabbitmq_channel = await connection.channel()
                return connection
            except aio_pika.exceptions.AMQPConnectionError as e:
                logger.warning(f"RabbitMQ connection attempt {i + 1} failed: {e}")
                await asyncio.sleep(2)
        raise RuntimeError("Could not connect to RabbitMQ after several attempts")

    async def _listen_to_rabbitmq(self):
        logger.info("[*] Connecting to RabbitMQ...")
        connection = await self.connect_rabbitmq()
        channel = await connection.channel()
        queue = await channel.declare_queue(self.model_name)

        logger.info(f"[*] Listening to queue: {self.model_name}")
        async for message in queue:
            await self._handle_message(message)

    async def _handle_message(self, message: IncomingMessage):
        async with message.process():
            logger.info(f"[*] Processing task for model: {self.model_name}")
            task = models_pb2.Task()
            task.ParseFromString(message.body)
            logger.info(f"Task ID: {task.task_id}")

            result = await self.process_request(task.request)
            task_id = task.task_id
            if ":" not in task_id:
                logger.warning("[!] Task ID does not contain user_id. Possible misconfiguration.")

            await self.redis.set(task_id, result.SerializeToString())
            logger.info(f"[*] Stored result in Redis with key: {task.task_id}")

    # -------------------- Registry --------------------
    def _register_with_registry(self):
        host = self.config["model_registry"]["host"]
        port = self.config["model_registry"]["port"]
        try:
            response = requests.post(
                f"http://{host}:{port}/register",
                params={"model_name": self.model_name, "host": self.host, "port": self.port}
            )
            logger.info(f"[*] Registered with registry: {response.json()}")
        except requests.RequestException as e:
            logger.error(f"[!] Failed to register: {e}")

    def _unregister_from_registry(self):
        host = self.config["model_registry"]["host"]
        port = self.config["model_registry"]["port"]
        try:
            response = requests.post(
                f"http://{host}:{port}/unregister",
                params={"model_name": self.model_name}
            )
            logger.info(f"[*] Unregistered from registry: {response.json()}")
        except requests.ConnectionError:
            logger.warning("[!] Registry unavailable, will unregister later.")
        except requests.RequestException as e:
            logger.error(f"[!] Unregister failed: {e}")

    # -------------------- Utils --------------------
    def _load_config(self, file_path: str):
        with open(file_path, "r") as f:
            return json.load(f)

    def _get_host_ip(self):
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "127.0.0.1"

    # -------------------- Multiprocessing Run --------------------
    def run(self):
        from multiprocessing import Process
        import uvicorn

        def run_api():
            uvicorn.run(self.app, host="0.0.0.0", port=self.port)

        async def run_worker_async():
            await self._connect_redis()
            await self._listen_to_rabbitmq()

        def run_worker():
            asyncio.run(run_worker_async())

        api_process = Process(target=run_api)
        worker_process = Process(target=run_worker)

        api_process.start()
        worker_process.start()

        api_process.join()
        worker_process.join()

    # -------------------- Generic Descriptor Access --------------------
    def get_request_format(self):
        return self.request_cls.DESCRIPTOR

    def get_response_format(self):
        return self.response_cls.DESCRIPTOR

    # -------------------- Abstract Method --------------------
    @abstractmethod
    async def process_request(self, body: bytes) -> ResponseType:
        """
        Implement this method to process incoming requests.
        Must return a Protobuf message instance.
        """
        pass
