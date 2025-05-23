from interface import BaseModel
import models_pb2
import uvicorn
import time


class ModelB(BaseModel):
    async def process_request(self, body):
        model_b_request = models_pb2.ModelBRequest()
        model_b_request.ParseFromString(body)
        response_obj = models_pb2.ModelBResponse()
        response_obj.status = f"Stored value: {model_b_request.value}"
        time.sleep(30)
        return response_obj

    def get_request_format(self):
        return models_pb2.ModelBRequest.DESCRIPTOR

    def get_response_format(self):
        return models_pb2.ModelBResponse.DESCRIPTOR


if __name__ == "__main__":
    uvicorn.run(ModelB("ModelB", 8001).app, host="0.0.0.0", port=8001)
