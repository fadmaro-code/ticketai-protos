import sys
import grpc
import json
import logging
from concurrent import futures

from bson import json_util

sys.path.insert(0, "/search/src/service/search")

from search_pb2 import SearchDocumentsRequest, SearchDocumentsResponse
from search_pb2_grpc import SearchDocumentsServicer, add_SearchDocumentsServicer_to_server

from search.search import simple_search


class GRPCSearchDocuments(SearchDocumentsServicer):
    def simpleSearch(self, request, context):
        ids = simple_search(
            terms=request.searchTerms,
            index=request.index,
            user_id=request.userId,
            fields=[field for field in request.fields],
            fuzziness=request.fuzziness,
        )
        return SearchDocumentsResponse(ids=list(ids))


def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=32), maximum_concurrent_rpcs=160)
    add_SearchDocumentsServicer_to_server(GRPCSearchDocuments(), server)
    server.add_insecure_port("[::]:50053")
    print("Starting dataset gRPC server listening at '[::]:50053'...")
    server.start()
    server.wait_for_termination()


if __name__ == "__main__":
    logging.basicConfig()
    try:
        serve()
    except Exception as e:
        print(e)
        print("GRPCSearchDocuments server is running somewhere else...")
