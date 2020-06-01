import sys
import datetime

sys.path.insert(0, "/ocr/src/service/ocr")
sys.path.insert(0, "/search/src/service/ocr")
sys.path.insert(0, "/api-gateway/src/service/ocr")
sys.path.insert(0, "/transactions/src/service/ocr")

import grpc
from google.protobuf.timestamp_pb2 import Timestamp

import json

from service.ocr.dataset_pb2_grpc import DatasetStub
from service.ocr.dataset_pb2 import (
    GetOneDocumentRequest,
    GetManyDocumentsRequest,
    DocumentResponse,
    GetOneDocumentInfoRequest,
    GetManyDocumentsInfoRequest,
    GetAllDocumentsInfoRequest,
    GetOneDocumentImageRequest,
    UpdateDocumentLinesRequest,
    UpdateLineRequest,
    GetOneLineCropRequest,
    GetDocumentsMetricsRequest,
)
from bson import ObjectId

server_name = "ocr"
port = "50052"

nested_fields = {"pages", "areas", "paragraphs", "lines", "words", "matches"}
nested_field = {"bbox", "top_left", "bottom_right"}


def pb_to_dict(pb):
    d = {}
    for descriptor, value in pb.ListFields():
        d[descriptor.name] = deserialize(descriptor, value)
    return d


def dt_to_pb(dt):
    pb = Timestamp()
    pb.FromDatetime(dt)
    return pb


def deserialize(descriptor, value):
    if descriptor.name in nested_fields:
        return [pb_to_dict(v) for v in value]
    if descriptor.name in nested_field:
        return pb_to_dict(value)
    if descriptor.name == "_id":
        return ObjectId(value)
    if descriptor.name in ["created_at", "updated_at"]:
        return value.ToDatetime()
    if descriptor.name in ["verified", "matches"]:
        return {k: v for k, v in value.items()}
    return value


class GRPCDatasetClient:
    stub = None
    channel = None

    def __init__(self):
        self.channel = grpc.insecure_channel(server_name + ":" + port)
        self.stub = DatasetStub(self.channel)

    def __del__(self):
        self.channel.close()

    def get_one_document(self, document_id, user_id):
        resp = self.stub.GetOneDocument(GetOneDocumentRequest(documentUuid=document_id, userId=user_id))
        return pb_to_dict(resp) if len(resp.ListFields()) else None

    def get_many_documents(self, document_ids, user_id):
        response_iterator = self.stub.GetManyDocuments(
            GetManyDocumentsRequest(documentUuids=document_ids, userId=user_id)
        )
        for resp in response_iterator:
            if len(resp.pages):
                yield pb_to_dict(resp)

    def get_one_document_info(self, document_id, user_id):
        resp = self.stub.GetOneDocumentInfo(
            GetOneDocumentInfoRequest(documentUuid=document_id, userId=user_id)
        )
        if len(resp.ListFields()):
            data = pb_to_dict(resp)
            data["verified"] = data.get("verified", False)
            return data
        return None

    def get_many_documents_info(self, document_ids, user_id):
        response_iterator = self.stub.GetManyDocumentsInfo(
            GetManyDocumentsInfoRequest(documentUuids=document_ids, userId=user_id)
        )
        for resp in response_iterator:
            if len(resp.ListFields()):
                data = pb_to_dict(resp)
                data["verified"] = data.get("verified", False)
                yield data

    def get_all_documents_info(
        self, user_id, skip=0, limit=100, start_date=None, end_date=None, with_matches="all"
    ):
        end_date = end_date or datetime.datetime.now()
        start_date = start_date or datetime.datetime.fromtimestamp(0)
        response_iterator = self.stub.GetAllDocumentsInfo(
            GetAllDocumentsInfoRequest(
                skip=skip,
                limit=limit,
                userId=user_id,
                startDate=dt_to_pb(start_date),
                endDate=dt_to_pb(end_date),
                withMatches=with_matches,
            )
        )
        for resp in response_iterator:
            if len(resp.ListFields()):
                data = pb_to_dict(resp)
                data["verified"] = data.get("verified", False)
                yield data

    def get_one_document_image(self, document_id, user_id):
        resp = self.stub.GetOneDocumentImage(
            GetOneDocumentImageRequest(documentUuid=document_id, userId=user_id)
        )
        return resp.image or None

    def update_document_lines(self, document_id, lines, user_id):
        line_requests = [UpdateLineRequest(text=l["text"], uuid=l["uuid"]) for l in lines]
        resp = self.stub.UpdateDocumentLines(
            UpdateDocumentLinesRequest(documentUuid=document_id, lines=line_requests, userId=user_id)
        )
        return resp.count

    def get_one_line_crop(self, document_id, line_id, user_id):
        resp = self.stub.GetOneLineCrop(
            GetOneLineCropRequest(documentUuid=document_id, lineUuid=line_id, userId=user_id)
        )
        return resp.image or None

    def get_documents_metrics(self, user_id, start_date=None, end_date=None):
        end_date = end_date or datetime.datetime.now()
        start_date = start_date or end_date - datetime.timedelta(days=1)

        resp = self.stub.GetDocumentsMetrics(
            GetDocumentsMetricsRequest(
                userId=user_id, startDate=dt_to_pb(start_date), endDate=dt_to_pb(end_date)
            )
        )
        return {
            "documents_total_count": resp.total or 0,
            "documents_matched_count": resp.matched or 0,
            "documents_matched_all_fields_count": resp.matched_all_fields or 0,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        }
