# pylint: disable=import-error
import os
import sys
import datetime

from logging import warning

sys.path.insert(0, "/user_identity/src/service/user_identity")
sys.path.insert(0, "/transactions/src/service/user_identity")
sys.path.insert(0, "/ocr/src/service/user_identity")
sys.path.insert(0, "/api-gateway/src/service/user_identity")

from bson import ObjectId

import grpc
from google.protobuf.timestamp_pb2 import Timestamp

from service.user_identity.user_identity_pb2_grpc import UserIdentityServiceStub
from service.user_identity.user_identity_pb2 import (
    CreateUserIdentityRequest,
    GetUserIdentityByUUIDRequest,
    UpdateUserIdentityRequest,
    DeleteUserIdentityRequest,
    CreateBranchOfficeIdentityRequest,
    GetBranchOfficeIdentityByUUIDRequest,
    UpdateBranchOfficeIdentityRequest,
    DeleteBranchOfficeIdentityRequest,
    CreateOrganizationIdentityRequest,
    GetOrganizationsRequest,
    GetOrganizationIdentityByUUIDRequest,
    UpdateOrganizationIdentityRequest,
    DeleteOrganizationIdentityRequest,
    GetBranchOfficesByEmailRequest,
    GetBranchOfficeAssociateListRequest,
    GetKratosUserIdentityRequest
)

server_name = "user_identity"
port = "50055"

# Chepe's way... This is the way.
nested_fields = {"users", "branch_offices"}
nested_field = {"branch_office", "organization"}

def serialized(info):
    items = {}
    for k, v in info.items():
        if k in include_fields:
            if k in keep_type:
                items[k] = v
            else:
                items[k] = str(v)
    return items

def pb_to_dict(pb):
    d = {}
    for descriptor, value in pb.ListFields():
        d[descriptor.name] = deserialize(descriptor, value)
    return d


def dt_to_pb(dt):
    pb = Timestamp()
    pb.FromDatetime(dt)
    return pb

include_fields = [
    "uuid",
    "name",
    "email"
]
keep_type = ["visible"]

def deserialize(descriptor, value):
    if descriptor.name in nested_fields:
        return [pb_to_dict(v) for v in value]
    if descriptor.name in nested_field:
        return pb_to_dict(value)
    if descriptor.name in ["created_at", "updated_at"]:
        return str(value.ToDatetime())
    if descriptor.name in ["users"]:
        return {k: v for k, v in value.items()}
    return value


class GRPCUserIdentityClient:
    stub = None
    channel = None

    def __init__(self):
        self.channel = grpc.insecure_channel(server_name + ":" + port)
        self.stub = UserIdentityServiceStub(self.channel)

    def __del__(self):
        self.channel.close()

    def create_user_identity(self, uuid, first_name, last_name, email, role, branch_office_uuid=None):
        
        response = self.stub.CreateUser(
            CreateUserIdentityRequest(
                uuid=uuid,
                first_name=first_name,
                last_name=last_name,
                email=email,
                role=role,
                branch_office_uuid=branch_office_uuid
            )
        )
        return response.uuid

    def get_user_identity_by_uuid(self, uuid):
        
        response = self.stub.GetUserByUUID(
            GetUserIdentityByUUIDRequest(
                uuid=uuid
            )
        )
        
        return pb_to_dict(response) if len(response.ListFields()) else None

    def update_user_identity(self, uuid, first_name, last_name, role, branch_office_uuid=None):
        
        response = self.stub.UpdateUser(
            UpdateUserIdentityRequest(
                uuid=uuid,
                first_name=first_name,
                last_name=last_name,
                role=role,
                branch_office_uuid=branch_office_uuid
            )
        )

        return response.uuid

    def delete_user_identity(self, uuid):
        
        user_identity_dict = dict()
        user_identity_dict["uuid"] = uuid

        response = self.stub.DeleteUser(
            DeleteUserIdentityRequest(
                uuid=uuid
            )
        )

        return response.uuid


    def create_branch_office_identity(self, name, street, number, city, state, zip_code, organization_uuid=None):
        
        response = self.stub.CreateBranchOffice(
            CreateBranchOfficeIdentityRequest(
                name=name,
                street=street,
                number=number,
                city=city,
                state=state,
                zip_code=zip_code,
                organization_uuid=organization_uuid
            )
        )

        return response.uuid

    def get_branch_office_identity_list(self, organization_domain):
        
        response_iterator = self.stub.GetBranchOfficesByEmail(
            GetBranchOfficesByEmailRequest(
                organization_domain=organization_domain
            )
        )
        
        for response in response_iterator:
            if len(response.name):
                yield pb_to_dict(response)

    def get_branch_office_identity_by_uuid(self, uuid):
        
        response = self.stub.GetBranchOfficeByUUID(
            GetBranchOfficeIdentityByUUIDRequest(
                uuid=uuid
            )
        )

        return pb_to_dict(response) if len(response.ListFields()) else None

    def update_branch_office_identity(self, uuid, name, street, number, city, state, zip_code):
        
        response = self.stub.UpdateBranchOffice(
            UpdateBranchOfficeIdentityRequest(
                    uuid=uuid,
                    name=name,
                    street=street,
                    number=number,
                    city=city,
                    state=state,
                    zip_code=zip_code
            )
        )

        return response.uuid

    def delete_branch_office_identity(self, uuid):
        
        response = self.stub.DeleteBranchOffice(
            DeleteBranchOfficeIdentityRequest(
                uuid=uuid
            )
        )

        return response.uuid
    

    def create_organization_identity(self, organization_domain, name):
        
        response = self.stub.CreateOrganization(
            CreateOrganizationIdentityRequest(
                organization_domain=organization_domain,
                name=name
            )
        )
        
        return response.uuid

    def get_organizations(self):
    
        response_iterator = self.stub.GetOrganizations(
            GetOrganizationsRequest()
        )
        
        for response in response_iterator:
            if len(response.name):
                yield pb_to_dict(response)

    
    def get_organization_identity_by_uuid(self, uuid):
        
        response = self.stub.GetOrganizationByUUID(
            GetOrganizationIdentityByUUIDRequest(
                uuid=uuid
            )
        )
        
        return pb_to_dict(response) if len(response.ListFields()) else None

    def update_organization_identity(self, uuid, organization_domain, name):
        
        response = self.stub.UpdateOrganization(
            UpdateOrganizationIdentityRequest(
                    uuid=uuid,
                    organization_domain=organization_domain,
                    name=name
            )
        )

        return response.uuid

    def delete_organization_identity(self, uuid):
        
        organization_identity_dict = dict()
        organization_identity_dict["uuid"] = uuid

        response = self.stub.DeleteOrganization(
            DeleteOrganizationIdentityRequest(
                uuid=uuid
            )
        )

        return response.uuid
    

    def get_branch_office_associate_list(self, user_uuid):
        
        if not user_uuid:
            return None

        # Mongo exclusive.
        if user_uuid == "root":
            return {}
        
        response_iterator = self.stub.GetBranchOfficeAssociateList(
            GetBranchOfficeAssociateListRequest(
                uuid=user_uuid
            )
        )

        branch_office_associate_list = self.response_generator(response_iterator)
        
        branch_office_associate_list = [serialized(info) for info in branch_office_associate_list]
        
        branch_office_associate_list = list(map(lambda d: d['email'], branch_office_associate_list))

        return branch_office_associate_list

    def response_generator(self, input_response_iterator):
        
        for input_response in input_response_iterator:
            if len(input_response.email):
                yield pb_to_dict(input_response)


    def get_kratos_user_identity(self, ory_kratos_cookie, type="email"):
        
        kratos_user_identity = self.stub.GetKratosUserIdentity(
            GetKratosUserIdentityRequest(
                ory_kratos_cookie=ory_kratos_cookie,
                type=type
            )
        )

        return kratos_user_identity.user_identity