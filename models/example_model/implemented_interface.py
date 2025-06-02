from interface import BaseModel
from transformers import pipeline
import models_pb2
import uvicorn
import io


class ExampleModel(BaseModel):

    def summarize_text_file(self, file):
        text = file.read()

        if not text.strip():
            print("The file is empty.")
            return

        text = "summarize: " + text.strip().replace("\n", " ")
        # Load summarization pipeline with a light model
        summarizer = pipeline("summarization", model="t5-small", tokenizer="t5-small")

        # t5-small can handle up to ~512 tokens, limit to ~800 characters
        max_chunk = 800
        chunks = [text[i:i + max_chunk] for i in range(0, len(text), max_chunk)]

        summaries = []
        for chunk in chunks:
            result = summarizer(chunk, max_length=100, min_length=30, do_sample=False)
            summaries.append(result[0]['summary_text'])

        final_summary = " ".join(summaries)
        return final_summary.strip()

    def get_file_from_bytes(self, file_bytes):
        file_like = io.BytesIO(file_bytes)
        return io.TextIOWrapper(file_like, encoding='utf-8')

    async def process_request(self, body):
        request = models_pb2.ExampleModelRequest()
        request.ParseFromString(body)
        response_obj = models_pb2.ExampleModelResponse()

        file = self.get_file_from_bytes(request.file.content)

        summary = self.summarize_text_file(file)

        response_obj.summary = summary
        response_obj.fixed_author = request.author + " (summarized by AI)"
        return response_obj

    def get_request_format(self):
        return models_pb2.ExampleModelRequest.DESCRIPTOR

    def get_response_format(self):
        return models_pb2.ExampleModelResponse.DESCRIPTOR


if __name__ == "__main__":
    uvicorn.run(ExampleModel("ExampleModel", 8003).app, host="0.0.0.0", port=8003)
