import grpc
import json
import logging
from concurrent import futures

from bson import json_util

from ocr_pb2 import TextDetectionRequest, TextDetectionResponse, JSONResponse
from ocr_pb2_grpc import TextDetectorServicer, add_TextDetectorServicer_to_server

from utils.image import bytes_to_image
from ocr.text_detector import TextDetector


class GRPCTextDetector(TextDetectorServicer):
    _detector = None

    @property
    def detector(self):
        if not self._detector:
            self._detector = TextDetector()
        return self._detector

    def detect(self, request, context):
        document = self.detector.detect(filename=request.filename, data=request.data)
        json_string = json.dumps(document.to_dict(), default=json_util.default)
        return JSONResponse(jsonString=json_string)


def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=32), maximum_concurrent_rpcs=160)
    add_TextDetectorServicer_to_server(GRPCTextDetector(), server)
    server.add_insecure_port("[::]:50051")
    print("Starting OCR gRPC server listening at '[::]:50051'...")
    server.start()
    server.wait_for_termination()


if __name__ == "__main__":
    logging.basicConfig()
    try:
        serve()
    except:
        print("GRPCTextDetector server is somewhere else...")
