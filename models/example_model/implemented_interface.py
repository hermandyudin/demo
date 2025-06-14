from interface import BaseModel
from transformers import pipeline
from models_pb2 import ExampleModelRequest, ExampleModelResponse
from io import BytesIO


class ExampleModel(BaseModel[ExampleModelRequest, ExampleModelResponse]):
    request_cls = ExampleModelRequest
    response_cls = ExampleModelResponse

    def summarize_text_file(self, file):
        text = file.read().decode("utf-8")

        if not text.strip():
            print("The file is empty.")
            return ""

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

    async def process_request(self, body):
        request = self.request_cls()
        request.ParseFromString(body)
        response_obj = self.response_cls()

        file = BytesIO(request.file.content)

        summary = self.summarize_text_file(file)

        response_obj.summary = summary
        response_obj.fixed_author = request.author + " (summarized by AI)"
        return response_obj


if __name__ == "__main__":
    model = ExampleModel("ExampleModel", 8003)
    model.run()
