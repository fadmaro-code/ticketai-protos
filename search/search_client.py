import sys

sys.path.insert(0, "/search/src/service/search")
sys.path.insert(0, "/api-gateway/src/service/search")

import grpc
import json

from service.search.search_pb2 import SearchDocumentsRequest
from service.search.search_pb2_grpc import SearchDocumentsStub

from utils.image import image_to_bytes

server_name = "search"
port = "50053"


class GRPCSearchDocumentsClient:
    stub = None
    channel = None

    def __init__(self):
        self.channel = grpc.insecure_channel(server_name + ":" + port)
        self.stub = SearchDocumentsStub(self.channel)

    def __del__(self):
        self.channel.close()

    def search_documents(self, search_terms, index, user_id, fuzziness=2, fields=[]):
        if isinstance(search_terms, str):
            search_terms = search_terms.split()

        resp = self.stub.simpleSearch(
            SearchDocumentsRequest(
                searchTerms=search_terms, index=index, userId=user_id, fuzziness=fuzziness, fields=fields
            )
        )
        return resp.ids
