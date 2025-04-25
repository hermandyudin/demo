from google.protobuf.descriptor import Descriptor
import base64
import json
from google.protobuf import descriptor_pb2, descriptor_pool

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
    """Generates OpenAPI paths for a given model based on schema references."""
    return {
        f"/models/{model_name}/tasks": {
            "post": {
                "summary": f"Submit task to {model_name}",
                "requestBody": {
                    "content": {
                        "application/json": {
                            "schema": {"$ref": request_schema_ref}
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
        },
        f"/models/{model_name}/result": {
            "get": {
                "summary": f"Get task result from {model_name}",
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
                                        "result": {"$ref": response_schema_ref}
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }


def fill_defaults_from_descriptor(descriptor: Descriptor):
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

    def _fill(desc: Descriptor):
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


def parse_descriptor(response_content):
    response_data = json.loads(response_content)
    message_name = response_data['message_name']
    descriptor_base64 = response_data['descriptor_bytes']
    descriptor_bytes = base64.b64decode(descriptor_base64)
    file_descriptor_proto = descriptor_pb2.FileDescriptorProto()
    file_descriptor_proto.ParseFromString(descriptor_bytes)
    pool = descriptor_pool.DescriptorPool()
    file_descriptor = pool.Add(file_descriptor_proto)
    message_descriptor = file_descriptor.message_types_by_name.get(message_name.split('.')[-1])

    return message_descriptor
