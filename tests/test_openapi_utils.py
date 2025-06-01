from utils.openapi_utils import (
    inject_static_schemas, generate_openapi_schema, generate_model_paths,
    fill_defaults_from_descriptor
)
from google.protobuf import descriptor_pb2


def test_inject_static_schemas_adds_user():
    schema = {"components": {"schemas": {}}}
    inject_static_schemas(schema)
    assert "User" in schema["components"]["schemas"]
    assert "HTTPValidationError" in schema["components"]["schemas"]


def test_generate_openapi_schema_from_nested_dict():
    data = {
        "name": "example",
        "attributes": {"score": 0.95, "active": True},
        "tags": ["a", "b"]
    }
    schema = generate_openapi_schema(data)
    assert schema["type"] == "object"
    assert "attributes" in schema["properties"]


def test_generate_model_paths_structure():
    paths = generate_model_paths("mymodel", "#/ref/request", "#/ref/response")
    assert "/models/mymodel/tasks" in paths
    assert "post" in paths["/models/mymodel/tasks"]


def test_fill_defaults_from_descriptor_handles_basic_fields():
    desc = descriptor_pb2.DescriptorProto()
    desc.name = "TestMsg"
    desc.field.add(name="field1", number=1, type=descriptor_pb2.FieldDescriptorProto.TYPE_STRING)
    desc.field.add(name="field2", number=2, type=descriptor_pb2.FieldDescriptorProto.TYPE_INT32)

    file_desc = descriptor_pb2.FileDescriptorProto()
    file_desc.name = "test.proto"
    file_desc.message_type.extend([desc])

    from google.protobuf import descriptor_pool
    pool = descriptor_pool.DescriptorPool()
    file = pool.Add(file_desc)
    result = fill_defaults_from_descriptor(file.message_types_by_name["TestMsg"])
    assert result == {"field1": "", "field2": 0}
