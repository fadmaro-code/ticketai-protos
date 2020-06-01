import sys
import datetime
import json
import base64

sys.path.insert(0, "/api-gateway/src/service/ocr")
sys.path.insert(0, "/api-gateway/src/service/transactions")
sys.path.insert(0, "/transactions/src/service/transactions")

import grpc
from google.protobuf.timestamp_pb2 import Timestamp

from service.transactions.transactions_pb2_grpc import TransactionsStub
from service.transactions.transactions_pb2 import (
    GetManyTransactionsRequest,
    GetAllTransactionsRequest,
    GetTransactionsMetricsRequest,
    GetMatchesReportRequest,
)

server_name = "transactions"
port = "50054"


def dt_to_pb(dt):
    pb = Timestamp()
    pb.FromDatetime(dt)
    return pb


class GRPCTransactionsClient:
    stub = None
    channel = None

    def __init__(self):
        self.channel = grpc.insecure_channel(server_name + ":" + port)
        self.stub = TransactionsStub(self.channel)

    def __del__(self):
        self.channel.close()

    def get_all_transactions(self, user_id, skip=0, limit=0, fields=None):
        response_iterator = self.stub.GetAllTransactions(
            GetAllTransactionsRequest(skip=skip, limit=limit, userId=user_id, fields=fields)
        )
        for resp in response_iterator:
            if len(resp.ListFields()):
                data = json.loads(resp.jsonString)
                yield data

    def get_many_transactions(self, user_id, transaction_uuids, fields=None):
        response_iterator = self.stub.GetManyTransactions(
            GetManyTransactionsRequest(userId=user_id, transactionIds=transaction_uuids, fields=fields)
        )
        for resp in response_iterator:
            if len(resp.ListFields()):
                data = json.loads(resp.jsonString)
                yield data

    def get_transactions_metrics(self, user_id, start_date=None, end_date=None):
        end_date = end_date or datetime.datetime.now()
        start_date = start_date or end_date - datetime.timedelta(days=1)

        resp = self.stub.GetTransactionsMetrics(
            GetTransactionsMetricsRequest(
                userId=user_id, startDate=dt_to_pb(start_date), endDate=dt_to_pb(end_date)
            )
        )
        return {
            "transactions_total_count": resp.total or 0,
            "transactions_matched_count": resp.matched or 0,
            "transactions_matched_all_fields_count": resp.matched_all_fields or 0,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        }

    def get_matches_report(self, user_id, start_date=None, end_date=None):
        end_date = end_date or datetime.datetime.now()
        start_date = start_date or end_date - datetime.timedelta(days=1)

        resp = self.stub.GetMatchesReport(
            GetMatchesReportRequest(
                userId=user_id, startDate=dt_to_pb(start_date), endDate=dt_to_pb(end_date)
            )
        )
        return resp.data
