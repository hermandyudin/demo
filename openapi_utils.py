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
