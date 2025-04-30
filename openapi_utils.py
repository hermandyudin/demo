# openapi_utils.py

from google.protobuf import descriptor_pb2, descriptor_pool, message_factory
import base64
import json

static_openapi_schemas = {
    "User": {
        "type": "object",
        "properties": {
            "username": {"type": "string"},
            "password": {"type": "string"},
        },
        "required": ["username", "password"]
    },
    "HTTPValidationError": {
        "type": "object",
        "properties": {
            "detail": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "loc": {
                            "type": "array",
                            "items": {"type": "string"}
                        },
                        "msg": {"type": "string"},
                        "type": {"type": "string"}
                    }
                }
            }
        }
    }
}


def inject_static_schemas(openapi_schema: dict):
    """Injects predefined static schemas like User and HTTPValidationError into the OpenAPI schema."""
    openapi_schema.setdefault("components", {}).setdefault("schemas", {}).update(static_openapi_schemas)


def generate_openapi_schema(data):
    """Recursively generates OpenAPI schema from a dictionary."""
    if isinstance(data, dict):
        return {
            "type": "object",
            "properties": {k: generate_openapi_schema(v) for k, v in data.items()}
        }
    elif isinstance(data, list):
        return {
            "type": "array",
            "items": generate_openapi_schema(data[0]) if data else {"type": "string"}
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


def generate_model_paths(model_name, request_schema_ref, response_schema_ref):
    return {
        f"/models/{model_name}/tasks": {
            "post": {
                "summary": f"Submit task to {model_name}",
                "requestBody": {
                    "content": {
                        "application/json": {
                            "schema": {"$ref": request_schema_ref}
                        },
                        "application/x-protobuf": {
                            "schema": {"type": "string", "format": "binary"}
                        }
                    },
                    "required": True
                },
                "responses": {
                    "200": {
                        "description": "Task submitted successfully",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "task_id": {"type": "string"}
                                    }
                                }
                            }
                        }
                    }
                },
                "security": [{"BearerAuth": []}]
            }
        },
        f"/models/{model_name}/result": {
            "get": {
                "summary": f"Get task result from {model_name}",
                "parameters": [
                    {
                        "name": "task_id",
                        "in": "query",
                        "required": True,
                        "schema": {"type": "string"}
                    }
                ],
                "responses": {
                    "200": {
                        "description": "Result of the task",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "task_id": {"type": "string"},
                                        "status": {"type": "string"},
                                        "result": {"$ref": response_schema_ref}
                                    }
                                }
                            },
                            "application/x-protobuf": {
                                "schema": {"type": "string", "format": "binary"}
                            }
                        }
                    }
                },
                "security": [{"BearerAuth": []}]
            }
        }
    }


def fill_defaults_from_descriptor(descriptor):
    """Fills a dictionary with default values based on a protobuf descriptor."""

    def _get_default_value(field):
        if field.cpp_type == field.CPPTYPE_STRING:
            return ""
        if field.cpp_type in (field.CPPTYPE_INT32, field.CPPTYPE_INT64):
            return 0
        if field.cpp_type == field.CPPTYPE_BOOL:
            return False
        if field.cpp_type in (field.CPPTYPE_FLOAT, field.CPPTYPE_DOUBLE):
            return 0.0
        return None

    def _fill(desc):
        result = {}
        for field in desc.fields:
            if field.label == field.LABEL_REPEATED:
                result[field.name] = (
                    [_fill(field.message_type)] if field.message_type else [_get_default_value(field)]
                )
            elif field.message_type:
                result[field.name] = _fill(field.message_type)
            else:
                result[field.name] = _get_default_value(field)
        return result

    return _fill(descriptor)


def bytes_to_protobuf(descriptor, byte_data):
    message_class = make_message_class(descriptor)
    message = message_class()
    message.ParseFromString(byte_data)
    return message


def parse_descriptor(response_content):
    """Parses a protobuf descriptor from base64 and returns the correct message descriptor."""
    response_data = json.loads(response_content)
    message_name = response_data['message_name']
    descriptor_base64 = response_data['descriptor_bytes']
    descriptor_bytes = base64.b64decode(descriptor_base64)

    # Parse FileDescriptorProto
    file_descriptor_proto = descriptor_pb2.FileDescriptorProto()
    file_descriptor_proto.ParseFromString(descriptor_bytes)

    # Use a new descriptor pool to avoid duplicate file issues
    pool = descriptor_pool.DescriptorPool()
    pool.Add(file_descriptor_proto)

    try:
        file_descriptor = pool.AddSerializedFile(descriptor_bytes)
    except Exception as e:
        raise ValueError(f"Failed to parse descriptor: {e}")

    # Extract the correct message descriptor
    message_descriptor = file_descriptor.message_types_by_name.get(message_name.split('.')[-1])

    if message_descriptor is None:
        raise ValueError(f"Message descriptor not found for: {message_name}")

    return message_descriptor


def json_to_protobuf(descriptor, json_data):
    """Convert a JSON dictionary into a Protobuf message based on a descriptor."""
    from google.protobuf.json_format import ParseDict

    message_class = make_message_class(descriptor)
    return ParseDict(json_data, message_class())


def protobuf_to_dict(proto_message):
    """Convert a Protobuf message to a dictionary."""
    from google.protobuf.json_format import MessageToDict
    return MessageToDict(proto_message, preserving_proto_field_name=True)


def make_message_class(descriptor):
    """Creates a Protobuf message class from a descriptor."""
    return message_factory.GetMessageClass(descriptor)
