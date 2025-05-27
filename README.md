# Demo System

## Overview

This project demonstrates a simple modular microservices architecture for serving machine learning models. It includes:

- A FastAPI-based API service
- Two independent models (`ModelA`, `ModelB`)
- A model registry for managing available models
- Messaging support via RabbitMQ
- Optional caching or async support via Redis

## Architecture

```mermaid
graph TD
    Client -->|Interacts with API| API_Service
    API_Service -->|Gets active models list and gets their i/o messages| Model_Registry
    API_Service -->|Puts new tasks to particular queue| RabbitMQ[RabbitMQ]
    API_Service -->|Gets result of the task from db| Redis[Redis]
    Any_Model -->|Registers itself| Model_Registry
    Model_Registry -->|Monitors if model is alive| Any_Model
    Any_Model -->|Puts result of the task| Redis
    Any_Model -->|Listens to queue and takes tasks| RabbitMQ

    classDef model fill:#f9f,stroke:#333,stroke-width:1px;
    class Any_Model model;
```

Each model is isolated and can be scaled or extended independently.

## Components

- `api_service.py`: Main HTTP entrypoint
- `model_registry.py`: Registers and retrieves models
- `model_a.py` / `model_b.py`: Example ML models
- `proto/`: Contains protobuf definitions for structured data
- `load_testing/`: Performance testing tools
- `serialization_type_test/`: Serialization format experiments

## How to Run

### Using Docker Compose

```bash
docker-compose up --build
```

### Available ports:

- `API Service`: localhost:8000

- `RabbitMQ Admin`: localhost:15672

- `Redis`: localhost:6379

## Sending a Prediction
```bash
curl -X POST http://localhost:8000/predict/model_a -H "Content-Type: application/json" -d '{"data": "example"}'
```

## Development
### Install dependencies and run locally:

```bash
pip install -r requirements.txt
python api_service.py
```

## Tests
```bash
pytest tests/
```

## Docker
To simplify local setup, each component can be containerized.

Dockerfile in project root (or per service)

docker-compose.yml defines how services connect

# How to add new model
Actually, there are only several things to make new model work:

1) Add input and output messages, that will represent i/o data for model to schema registry.
2) Implement process_request method of interface. This is the main method, that accepts request and produces result. Example:
```python
    async def process_request(self, body):
        model_a_request = models_pb2.ModelARequest()
        model_a_request.ParseFromString(body)
        response_obj = models_pb2.ModelAResponse()
        response_obj.reply = f"Processed message: {model_a_request.messages}\n"
        return response_obj
```
3) Implement get_request_format and get_response_format methods. They just return descriptors of messages:
```python
    def get_request_format(self):
        return models_pb2.ModelARequest.DESCRIPTOR

    def get_response_format(self):
        return models_pb2.ModelAResponse.DESCRIPTOR
```
4) Deploy model. Interface will do the rest of the work. It will register the model in model_registry and connect to RabbitMQ and Redis. It will start work!