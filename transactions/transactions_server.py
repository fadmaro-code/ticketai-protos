import os
import sys
import grpc
import json
import logging
import uuid
import base64
from concurrent import futures

from bson import json_util

sys.path.insert(0, "/transactions/src/service/transactions")

from transactions_pb2 import JSONResponse, TransactionsMetricsResponse, MatchesReportResponse
from transactions_pb2_grpc import TransactionsServicer, add_TransactionsServicer_to_server
from google.protobuf.timestamp_pb2 import Timestamp


from models.interface.mongodao import MongoDAO
from models.transaction_model import Transaction, TransactionSchema
from database.mongo import make_db
from utils.configmanager import ConfigManager
from tasks.transactions_handler import make_matches_report, write_df_to_xlsx

from service.user_identity.user_identity_client import GRPCUserIdentityClient

identity_grpc_client = GRPCUserIdentityClient()

transactions_summary = ["commerce_name", "invoice_number", "date", "total_sale", "expiration_date", "matches"]

transactions_details = transactions_summary + [
    "client_number",
    "branch",
    "invoice_amount",
    "promotional_discount",
    "physical_change",
    "invoice_value",
    "agreed_discount",
    "invoice_clean_amount",
    "ieps_tax",
    "iva_tax",
    "invoice_total",
    "matches",
]


class GRPCTransactions(TransactionsServicer):
    _dao = None

    def __init__(self):
        self._dao = MongoDAO(make_db(ConfigManager.get_config_value("database", "mongo"))["transaction"])

    def GetAllTransactions(self, request, context):
        filters = self._get_request_access_constraint(request)
        skip = request.skip or 0
        limit = request.limit or 50
        fields = list(request.fields) or transactions_summary
        transactions = self._dao.get_many_by(filters, skip=skip, limit=limit)
        transactions = TransactionSchema(many=True, only=fields).dump(transactions)
        for transaction in transactions:
            yield JSONResponse(jsonString=json.dumps(transaction))

    def GetManyTransactions(self, request, context):
        fields = list(request.fields) or transactions_details
        filters = self._get_request_access_constraint(request)
        filters["_id"] = {"$in": list(request.transactionIds)}
        transactions = self._dao.get_many_by(filters)
        transactions = TransactionSchema(many=True, only=fields).dump(transactions)
        for transaction in transactions:
            yield JSONResponse(jsonString=json.dumps(transaction))

    def GetTransactionsMetrics(self, request, context):
        filters = self._get_request_access_constraint(request)

        end_date = request.endDate.ToDatetime()
        start_date = request.startDate.ToDatetime()
        filters["created_at"] = {"$gte": start_date, "$lte": end_date}
        total = self._dao.count(filters)

        filters["matches"] = {"$not": {"$size": 0}}
        matched = self._dao.count(filters)

        filters = self._get_request_access_constraint(request)
        filters["created_at"] = {"$gte": start_date, "$lte": end_date}
        filters["matches.line_qualities.branch"] = {"$in": ["A", "B"]}
        filters["matches.line_qualities.date"] = {"$in": ["A", "B"]}
        filters["matches.line_qualities.invoice_total"] = {"$in": ["A", "B"]}
        filters["matches.line_qualities.client_number"] = {"$in": ["A", "B"]}
        matched_all_fields = self._dao.count(filters)
        return TransactionsMetricsResponse(
            total=total, matched=matched, matched_all_fields=matched_all_fields
        )

    def GetMatchesReport(self, request, context):
        end_date = request.endDate.ToDatetime()
        start_date = request.startDate.ToDatetime()
        filters = self._get_request_access_constraint(request)
        filters["matches"] = {"$not": {"$size": 0}}
        filters["created_at"] = {"$gte": start_date, "$lte": end_date}
        print("writing report...")
        report = make_matches_report(filters)
        print("report written")
        path = "/tmp/" + str(uuid.uuid4()) + ".xlsx"
        write_df_to_xlsx(report, path)
        with open(path, "rb") as f:
            data = f.read()
        os.remove(path)
        return MatchesReportResponse(data=data)

    @staticmethod
    def _get_request_access_constraint(request):
        user_id = request.userId
        if user_id == "root":
            return {}
        constraint = {'user_id': {'$in': identity_grpc_client.get_branch_office_associate_list(user_id)}}
        return constraint


def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=32), maximum_concurrent_rpcs=160)
    add_TransactionsServicer_to_server(GRPCTransactions(), server)
    server.add_insecure_port("[::]:50054")
    print("Starting transactions gRPC server listening at '[::]:50054'...")
    server.start()
    server.wait_for_termination()


if __name__ == "__main__":
    logging.basicConfig()
    serve()
