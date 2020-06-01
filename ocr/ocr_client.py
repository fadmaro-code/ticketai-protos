import sys

sys.path.insert(0, "/ocr/src/service/ocr")
sys.path.insert(0, "/api-gateway/src/service/ocr")

import grpc
import json

from service.ocr.ocr_pb2 import TextDetectionRequest, JSONResponse
from service.ocr.ocr_pb2_grpc import TextDetectorStub

from utils.image import image_to_bytes

server_name = "ocr"
port = "50051"


class GRPCTextDetectorClient:
    stub = None
    channel = None

    def __init__(self):
        self.channel = grpc.insecure_channel(server_name + ":" + port)
        self.stub = TextDetectorStub(self.channel)

    def __del__(self):
        self.channel.close()

    def detect(self, filename, data):
        if type(data) is not bytes and type(data) is not bytearray:
            data = image_to_bytes(data)
        resp = self.stub.detect(TextDetectionRequest(filename=filename, data=data))
        return json.loads(resp.jsonString)
