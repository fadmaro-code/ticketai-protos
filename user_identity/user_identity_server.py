# pylint: disable=import-error
# pylint: disable=no-name-in-module
import os
import sys
import datetime
import grpc
import json
import logging
import base64
import asyncio
import aiohttp
from concurrent import futures

from bson import json_util

sys.path.insert(0, "/user_identity/src/service/user_identity")

from user_identity_pb2 import (
    CreateUserIdentityResponse,
    GetUserIdentityByUUIDResponse,
    UpdateUserIdentityResponse,
    DeleteUserIdentityResponse,

    CreateBranchOfficeIdentityResponse,
    GetBranchOfficeIdentityByUUIDResponse,
    UpdateBranchOfficeIdentityResponse,
    DeleteBranchOfficeIdentityResponse,
    
    CreateOrganizationIdentityResponse,
    GetOrganizationsResponse,
    GetOrganizationIdentityByUUIDResponse,
    UpdateOrganizationIdentityResponse,
    DeleteOrganizationIdentityResponse,

    GetBranchOfficesByEmailResponse,
    GetBranchOfficeAssociateListResponse,
    GetKratosUserIdentityResponse
)

from user_identity_pb2_grpc import UserIdentityServiceServicer, add_UserIdentityServiceServicer_to_server
from google.protobuf.timestamp_pb2 import Timestamp

from user_identity_pb2 import (
    UserMessage,
    BranchOfficeMessage,
    OrganizationMessage
)

from models.users import Users
from models.branch_office import BranchOffice
from models.organization import Organization
from models.schemas.identity_schema import (
    UserSchema,
    BranchOfficeSchema,
    OrganizationSchema
)

from marshmallow.exceptions import ValidationError

from utils.configmanager import ConfigManager

from logging import warning

# Policy URL.
keto_url = os.environ["KETO_URL"]
kratos_admin_url = os.environ["KRATOS_ADMIN_URL"]
kratos_public_url = os.environ["KRATOS_PUBLIC_URL"]

# Chepe's way... This is the way.
nested_fields = {
    "users": UserMessage,
    "branch_offices": BranchOfficeMessage
}
nested_field = {
    "user_identity": UserMessage,
    "branch_office": BranchOfficeMessage,
    "organization": OrganizationMessage
}

def dt_to_pb(dt_str):
    
    dt, _, us= dt_str.partition(".")
    dt= datetime.datetime.strptime(dt, "%Y-%m-%dT%H:%M:%S")
    us= int(us.rstrip("Z"), 10)
    dt = dt + datetime.timedelta(microseconds=us)

    pb = Timestamp()
    pb.FromDatetime(dt)
    return pb

def make_pb(d, message_type):

    for key, value in d.items():
        if key in nested_fields and value is not None:
            d[key] = [make_pb(item, nested_fields[key]) for item in d[key]]
        if key in nested_field and value is not None:
            d[key] = make_pb(value, nested_field[key])
        if key in ["created_at", "updated_at"] and value is not None:
            d[key] = dt_to_pb(value)
    return message_type(**d)


class GRPCUserIdentity(UserIdentityServiceServicer):

    def CreateUser(self, request, context):
        
        try:
            user_dict = dict()
            user_dict["uuid"] = request.uuid
            user_dict["first_name"] = request.first_name
            user_dict["last_name"] = request.last_name
            user_dict["email"] = request.email
            user_dict["role"] = request.role or "associate"
            
            if request.branch_office_uuid:
                user_dict["branch_office"] = dict()
                user_dict["branch_office"]["uuid"] = request.branch_office_uuid

                branch_office_identity = BranchOffice.get_identity_resource(
                    {
                        "uuid": request.branch_office_uuid,
                        "visible": True
                    }
                )

                if not branch_office_identity:
                    return make_pb({}, CreateUserIdentityResponse)

            user_identity = Users.get_identity_resource(
                {
                    "uuid": request.uuid,
                    "visible": False
                }
            )
            if user_identity:

                user_identity.first_name = request.first_name
                user_identity.last_name = request.last_name
                user_identity.email = request.email
                user_identity.role = request.role or "associate"
                user_identity.branch_office_uuid = request.branch_office_uuid

                user_identity.updated_at = datetime.datetime.now()
                user_identity.visible = True

                user_identity.save()
            else:
                
                user_identity = UserSchema().load(user_dict)
                user_identity.save()

        except Exception as e:
            warning(e)
            raise e
        
        try:
            loop = asyncio.new_event_loop()
            loop.run_until_complete(add_user_role(user_identity.uuid, user_identity.role))
        except Exception as e:
            warning(e)
            raise e
        return CreateUserIdentityResponse(uuid=user_identity.uuid)

    def GetUserByUUID(self, request, context):
        
        user_identity = Users.get_identity_resource(
            {
                "uuid": request.uuid,
                "visible": True
            }
        )
        
        user_identity = UserSchema().dump(user_identity)
        return make_pb(user_identity or {}, GetUserIdentityByUUIDResponse)
    
    def UpdateUser(self, request, context):

        try:
            
            user_identity = Users.get_identity_resource(
                {
                    "uuid": request.uuid,
                    "visible": True
                }
            )

            if not user_identity:
                return make_pb({}, UpdateUserIdentityResponse)
            
            if request.branch_office_uuid:

                branch_office_identity = BranchOffice.get_identity_resource(
                    {
                        "uuid": request.branch_office_uuid,
                        "visible": True
                    }
                )

                if not branch_office_identity:
                    return make_pb({}, UpdateUserIdentityResponse)

            old_role = user_identity.role

            if old_role != request.role:

                loop = asyncio.new_event_loop()
                loop.run_until_complete(delete_user_role(request.uuid, old_role))
            
            user_identity.first_name =request.first_name
            user_identity.last_name = request.last_name
            user_identity.role = request.role or "associate"
            user_identity.branch_office_uuid = request.branch_office_uuid
            user_identity.updated_at = datetime.datetime.now()

            user_identity.save()
            
            if old_role != request.role:
                loop.run_until_complete(add_user_role(request.uuid, request.role))

        except Exception as e:
            warning(e)
            raise e
        
        return UpdateUserIdentityResponse(uuid=user_identity.uuid)
    
    def DeleteUser(self, request, context):
        
        try:
            
            filter_dict = dict()
            filter_dict["uuid"] = request.uuid

            user_identity = Users.get_identity_resource(filter_dict)

            if not user_identity:
                return DeleteUserIdentityResponse(uuid=user_identity)

            old_role = user_identity.role

            loop = asyncio.new_event_loop()
            loop.run_until_complete(delete_user_role(filter_dict["uuid"], old_role))

            user_identity.disable()
        
        except Exception as e:
            warning(e)
            raise e

        return DeleteUserIdentityResponse(uuid=user_identity.uuid)


    def CreateBranchOffice(self, request, context):
        
        try:

            branch_office_dict = dict()
            branch_office_dict["name"] = request.name
            branch_office_dict["street"] = request.street
            branch_office_dict["number"] = request.number
            branch_office_dict["city"] = request.city
            branch_office_dict["state"] = request.state
            branch_office_dict["zip_code"] = request.zip_code
            branch_office_dict["organization"] = dict()
            branch_office_dict["organization"]["uuid"] = request.organization_uuid
            
            organization_identity = Organization.get_identity_resource(
                {
                    "uuid": request.organization_uuid,
                    "visible": True
                }
            )

            if not organization_identity:
                return make_pb({}, CreateBranchOfficeIdentityResponse)

            branch_office_identity = BranchOfficeSchema().load(branch_office_dict)
            branch_office_identity.save()

        except Exception as e:
            warning(e)
            raise e

        return CreateBranchOfficeIdentityResponse(uuid=branch_office_identity.uuid)

    def GetBranchOfficeByUUID(self, request, context):
        
        branch_office_identity = BranchOffice.get_identity_resource(
            {
                "uuid": request.uuid,
                "visible": True
            }
        )
        
        branch_office_identity = BranchOfficeSchema().dump(branch_office_identity)
        
        return make_pb(branch_office_identity or {}, GetBranchOfficeIdentityByUUIDResponse)
    
    def UpdateBranchOffice(self, request, context):
        
        try:

            branch_office_identity = BranchOffice.get_identity_resource(
                {
                    "uuid": request.uuid,
                    "visible": True
                }
            )

            if not branch_office_identity:
                return make_pb({}, UpdateBranchOfficeIdentityResponse)
            
            branch_office_identity.name = request.name
            branch_office_identity.street = request.street
            branch_office_identity.number = request.number
            branch_office_identity.city = request.city
            branch_office_identity.state = request.state
            branch_office_identity.zip_code = request.zip_code
            branch_office_identity.updated_at = datetime.datetime.now()

            branch_office_identity.save()

        except Exception as e:
            warning(e)
            raise e

        return UpdateBranchOfficeIdentityResponse(uuid=branch_office_identity.uuid)

    def DeleteBranchOffice(self, request, context):
        
        try:
            filter_dict = dict()
            filter_dict["uuid"] = request.uuid

            branch_office_identity = BranchOffice.get_identity_resource(filter_dict)

            if not branch_office_identity:
                return DeleteBranchOfficeIdentityResponse(uuid=branch_office_identity)
            
            branch_office_identity.disable()
        
        except Exception as e:
            warning(e)
            raise e

        return DeleteBranchOfficeIdentityResponse(uuid=branch_office_identity.uuid)


    def CreateOrganization(self, request, context):
        
        try:
            organization_dict = dict()
            organization_dict["organization_domain"] = request.organization_domain
            organization_dict["name"] = request.name
            organization_identity = OrganizationSchema().load(organization_dict)
            organization_identity.save()

        except Exception as e:
            warning(e)
            raise e

        return CreateOrganizationIdentityResponse(uuid=organization_identity.uuid)

    def GetOrganizations(self, request, context):
        
        organization_identities = Organization.get_all()
        
        organization_identities_dict = OrganizationSchema(many=True).dump(organization_identities)
        
        for organization_identity in organization_identities_dict:
            yield make_pb(organization_identity or {}, GetOrganizationsResponse)

    def GetOrganizationByUUID(self, request, context):
        
        organization_identity = Organization.get_identity_resource(
            {
                "uuid": request.uuid,
                "visible": True
            }
        )
        
        organization_identity = OrganizationSchema().dump(organization_identity)
        warning(organization_identity)
        return make_pb(organization_identity or {}, GetOrganizationIdentityByUUIDResponse)

    def UpdateOrganization(self, request, context):

        try:

            organization_identity = Organization.get_identity_resource(
                {
                    "uuid": request.uuid,
                    "visible": True
                }
            )

            if not organization_identity:
                return make_pb({}, UpdateOrganizationIdentityResponse)
            
            organization_identity.organization_domain = request.organization_domain
            organization_identity.name = request.name

            organization_identity.save()

        except Exception as e:
            warning(e)
            raise e

        return UpdateOrganizationIdentityResponse(uuid=organization_identity.uuid)

    def DeleteOrganization(self, request, context):

        try:
            filter_dict = dict()
            filter_dict["uuid"] = request.uuid

            organization_identity = Organization.get_identity_resource(filter_dict)

            if not organization_identity:
                return DeleteOrganizationIdentityResponse(uuid=organization_identity)
            
            organization_identity.disable()
        
        except Exception as e:
            warning(e)
            raise e

        return DeleteOrganizationIdentityResponse(uuid=organization_identity.uuid)


    def GetBranchOfficesByEmail(self, request, context):
        
        filter_dict = dict()
        filter_dict["organization_domain"] = request.organization_domain
        filter_dict["visible"] = True
        
        organization_identity = Organization.get_identity_resource(filter_dict)
        organization_identity_dict = OrganizationSchema(only=("branch_offices",)).dump(organization_identity)

        branch_office_identity_list = BranchOfficeSchema(many=True, only=("uuid", "name")).dump(organization_identity_dict["branch_offices"])
        
        for branch_office_identity in branch_office_identity_list:
            yield make_pb(branch_office_identity or {}, GetBranchOfficesByEmailResponse)


    def GetBranchOfficeAssociateList(self, request, context):
            
        user_identity = Users.get_identity_resource(
            {
                "email": request.uuid,
                "visible": True
            }
        )

        if not user_identity:
            yield make_pb({}, GetBranchOfficeAssociateListResponse)

        if user_identity.branch_office_uuid:

            branch_office_identity = BranchOffice.get_identity_resource(
                {
                    "uuid": user_identity.branch_office_uuid
                }
            )
        
        if not branch_office_identity:
            yield make_pb({}, GetBranchOfficeAssociateListResponse)

        branch_office_identity = BranchOfficeSchema(only=["users.email"]).dump(branch_office_identity)
        
        for branch_office_associate_identity in branch_office_identity["users"]:
            
            yield make_pb(branch_office_associate_identity or {}, GetBranchOfficeAssociateListResponse)

    
    def GetKratosUserIdentity(self, request, context):
        
        loop = asyncio.new_event_loop()
        
        kratos_user_identity = loop.run_until_complete(get_kratos_user_identity(request.ory_kratos_cookie, request.type))
        
        return GetKratosUserIdentityResponse(user_identity=kratos_user_identity)


def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=32), maximum_concurrent_rpcs=160)
    add_UserIdentityServiceServicer_to_server(GRPCUserIdentity(), server)
    server.add_insecure_port("[::]:50055")
    print("Starting user_identity gRPC server listening at '[::]:50055'...")
    server.start()
    server.wait_for_termination()

async def add_user_role(user_uuid, role):
    endpoint = f'/engines/acp/ory/exact/roles/{role}/members'
    headers = {
        'Content-Type': 'application/json'
    }
    data = {
        "members": [user_uuid]
    }
    url = f'{keto_url}{endpoint}'
    async with aiohttp.ClientSession() as session:
        async with session.put(url, headers=headers, json=data) as response:
            data = await response.json()
            return data

async def delete_user_role(user_uuid, role):
    endpoint = f'/engines/acp/ory/exact/roles/{role}/members/{user_uuid}'
    url = f'{keto_url}{endpoint}'
    
    async with aiohttp.ClientSession() as session:
        async with session.delete(url) as response:
            data = await response.json()
            return data

async def get_kratos_user_list():
    endpoint = f'/identities/'
    headers = {
        'Content-Type': 'application/json'
    }
    url = f'{kratos_admin_url}{endpoint}'

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as response:
            data = await response.json()
            return data

async def get_kratos_user_identity(request_cookie, type):
    if request_cookie:
        endpoint = f'/sessions/whoami'
        headers = {
            'Cookie': f'ory_kratos_session={request_cookie}'
        }
        url = f'{kratos_public_url}{endpoint}'
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                data = await response.json()
                return data["identity"]["traits"]["email"] if type == 'email' else data["identity"]["id"]

    elif os.environ['ENVIRONMENT'] == 'development':
        return os.environ['DEVELOPMENT_USER_ID']
    else:
        return 404

if __name__ == "__main__":
    logging.basicConfig()
    serve()
