from interface import BaseModel
from models_pb2 import ModelARequest, ModelAResponse


class ModelA(BaseModel[ModelARequest, ModelAResponse]):
    request_cls = ModelARequest
    response_cls = ModelAResponse

    async def process_request(self, body):
        model_a_request = self.request_cls()
        model_a_request.ParseFromString(body)  # Correct deserialization
        response_obj = self.response_cls()
        response_obj.reply = f"Processed message: {model_a_request.messages}\n"
        return response_obj


if __name__ == "__main__":
    model = ModelA("ModelA", 8000)
    model.run()
