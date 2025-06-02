# Dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY proto/ ./proto/

RUN python -m grpc_tools.protoc \
    -I proto \
    --python_out=. \
    --grpc_python_out=. \
    proto/models.proto

COPY . .

CMD ["python", "api_service.py"]