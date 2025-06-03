import asyncio

from interface import BaseModel
from models_pb2 import ModelBRequest, ModelBResponse


class ModelB(BaseModel[ModelBRequest, ModelBResponse]):
    request_cls = ModelBRequest
    response_cls = ModelBResponse

    async def process_request(self, body):
        model_b_request = self.request_cls()
        model_b_request.ParseFromString(body)
        response_obj = self.response_cls()
        response_obj.status = f"Stored value: {model_b_request.value}"
        await asyncio.sleep(30)
        return response_obj


if __name__ == "__main__":
    model = ModelB("ModelB", 8004)
    model.run()
