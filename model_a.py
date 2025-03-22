from interface import BaseModel
import models_pb2
import uvicorn


class ModelA(BaseModel):
    async def process_request(self, body):
        model_a_request = models_pb2.ModelARequest()
        model_a_request.ParseFromString(body)  # Correct deserialization
        response_obj = models_pb2.ModelAResponse()
        response_obj.reply = f"Processed message: {model_a_request.message}"
        return response_obj

    def get_request_descriptor(self):
        return models_pb2.ModelARequest.DESCRIPTOR

    def get_response_descriptor(self):
        return models_pb2.ModelAResponse.DESCRIPTOR


if __name__ == "__main__":
    uvicorn.run(ModelA("config.json", "ModelA", 8000).app, host="0.0.0.0", port=8000)