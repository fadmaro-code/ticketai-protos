import grpc
import logging
import datetime
from concurrent import futures

from bson import json_util, ObjectId
import string

from models.hocr import Document, Page
from models.interface.mongodao import MongoDAO
from database.mongo import make_db
from utils.configmanager import ConfigManager

from dataset_pb2 import (
    DocumentInfoResponse,
    DocumentResponse,
    PageResponse,
    AreaResponse,
    ParagraphResponse,
    LineResponse,
    WordResponse,
    BoundingBoxResponse,
    PointResponse,
    DocumentImageResponse,
    UpdateDocumentLinesResponse,
    MatchResponse,
    DocumentsMetricsResponse,
)
from dataset_pb2_grpc import DatasetServicer, add_DatasetServicer_to_server
from google.protobuf.timestamp_pb2 import Timestamp
from google.protobuf.struct_pb2 import Struct
from utils.files import extension
from utils.image import DATA_URL_PREFIX, image_to_base64
from tasks.dataset_event_handler import (
    retrieve_image,
    make_image_route,
    _update_document_lines,
    line_generator,
)  # TODO: Refactor location of functions

from logging import warning
from service.user_identity.user_identity_client import GRPCUserIdentityClient

identity_grpc_client = GRPCUserIdentityClient()

nested_fields = {
    "pages": PageResponse,
    "areas": AreaResponse,
    "paragraphs": ParagraphResponse,
    "lines": LineResponse,
    "words": WordResponse,
    "matches": MatchResponse,
}

nested_field = {
    "bbox": BoundingBoxResponse,
    "top_left": PointResponse,
    "bottom_right": PointResponse,
}


def dt_to_pb(dt):
    pb = Timestamp()
    pb.FromDatetime(dt)
    return pb


def document_info_handler(d, message_type):
    verified = d.pop("verified", False)
    if not verified:
        return d
    s = Struct()
    s.update(verified)
    d["verified"] = s
    return d


def make_pb(d, message_type, special_cases_handler=None):
    if special_cases_handler:
        d = special_cases_handler(d, message_type)
    for key, value in d.items():
        if key in nested_fields:
            d[key] = [make_pb(item, nested_fields[key]) for item in d[key]]
        if key in nested_field:
            d[key] = make_pb(value, nested_field[key])
        if isinstance(value, ObjectId):
            d[key] = str(value)
        if isinstance(value, datetime.datetime):
            d[key] = dt_to_pb(value)
    return message_type(**d)


class GRPCDataset(DatasetServicer):
    _db = None
    _doc_dao = None
    _info_dao = None

    def __init__(self):
        self._db = make_db(ConfigManager.get_config_value("database", "mongo-dataset"))
        self._doc_dao = MongoDAO(self._db["documents"])
        self._info_dao = MongoDAO(self._db["dataset"])

    def GetOneDocument(self, request, context):
        filters = self._get_request_access_constraint(request)
        filters["uuid"] = request.documentUuid
        document = self._doc_dao.get_first(filters=filters)
        return make_pb(document or {}, DocumentResponse)

    def GetManyDocuments(self, request, context):
        filters = self._get_request_access_constraint(request)
        filters["uuid"] = {"$in": list(request.documentUuids)}
        documents = self._doc_dao.get_many_by(filters)
        for document in documents:
            yield make_pb(document, DocumentResponse)

    def GetOneDocumentInfo(
        self, request, context,
    ):
        filters = self._get_request_access_constraint(request)
        filters["uuid"] = request.documentUuid
        doc_info = self._info_dao.get_first(filters)
        return make_pb(doc_info or {}, DocumentInfoResponse, document_info_handler)

    def GetManyDocumentsInfo(self, request, context):
        filters = self._get_request_access_constraint(request)
        filters["uuid"] = {"$in": list(request.documentUuids)}
        docs_info = self._info_dao.get_many_by(filters)
        for info in docs_info:
            yield make_pb(info, DocumentInfoResponse, document_info_handler)

    def GetAllDocumentsInfo(self, request, context):
        end_date = request.endDate.ToDatetime()
        start_date = request.startDate.ToDatetime()
        with_matches = request.withMatches
        filters = self._get_request_access_constraint(request)
        filters["created_at"] = {"$gte": start_date, "$lte": end_date}
        if with_matches == False:
            filters["matches"] = {"$size": 0}
        if with_matches == True:
            filters["matches"] = {"$not": {"$size": 0}}
        docs_info = self._info_dao.get_many_by(
            filters=filters, skip=request.skip, limit=request.limit, sort_by="created_at"
        )
        for info in docs_info:
            yield make_pb(info, DocumentInfoResponse, document_info_handler)

    def GetOneDocumentImage(self, request, context):
        filters = self._get_request_access_constraint(request)
        filters["uuid"] = request.documentUuid
        info = self._info_dao.get_first(filters)
        if not info:
            return DocumentImageResponse(image="")
        route = make_image_route(info)
        img = retrieve_image(route)
        if img:
            return DocumentImageResponse(image=image_to_base64(img, prefix=DATA_URL_PREFIX))
        return DocumentImageResponse(image="")

    def UpdateDocumentLines(self, request, context):
        filters = self._get_request_access_constraint(request)
        doc_info = self._info_dao.get_first(filters)
        if not doc_info:
            return UpdateDocumentLinesResponse(count=0)

        updated_count = _update_document_lines(
            request.documentUuid,
            [{"text": line.text, "uuid": line.uuid} for line in request.lines],
            request.userId,
        )
        return UpdateDocumentLinesResponse(count=updated_count)

    def GetOneLineCrop(self, request, context):
        filters = self._get_request_access_constraint(request)
        filters["uuid"] = request.documentUuid
        document = self._doc_dao.get_first(filters)
        if not document:
            return DocumentImageResponse(image="")

        document = Document.from_dict(document)
        for line in line_generator(document):
            if line.uuid == request.lineUuid:
                info = self._info_dao.get_first({"uuid": request.documentUuid})
                route = make_image_route(info)
                image = retrieve_image(route)
                if image:
                    return DocumentImageResponse(
                        image=image_to_base64(line.crop(image), prefix=DATA_URL_PREFIX)
                    )
        return DocumentImageResponse(image="")

    def GetDocumentsMetrics(self, request, context):
        filters = self._get_request_access_constraint(request)

        end_date = request.endDate.ToDatetime()
        start_date = request.startDate.ToDatetime()
        filters["created_at"] = {"$gte": start_date, "$lte": end_date}
        total = self._info_dao.count(filters)

        filters["matches"] = {"$not": {"$size": 0}}
        matched = self._info_dao.count(filters)
        return DocumentsMetricsResponse(total=total, matched=matched, matched_all_fields=matched)

    @staticmethod
    def _get_request_access_constraint(request):
        user_id = request.userId
        if user_id == "root":
            return {}
        constraint = {'user_id': {'$in': identity_grpc_client.get_branch_office_associate_list(user_id)}}
        return constraint


def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=32), maximum_concurrent_rpcs=160)
    add_DatasetServicer_to_server(GRPCDataset(), server)
    server.add_insecure_port("[::]:50052")
    print("Starting dataset gRPC server listening at '[::]:50052'...")
    server.start()
    server.wait_for_termination()


if __name__ == "__main__":
    logging.basicConfig()
    try:
        serve()
    except:
        print("GRPCDataset server is somewhere else...")
