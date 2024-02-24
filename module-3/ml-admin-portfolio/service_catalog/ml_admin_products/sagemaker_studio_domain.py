# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# SPDX-License-Identifier: MIT-0
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of this
# software and associated documentation files (the "Software"), to deal in the Software
# without restriction, including without limitation the rights to use, copy, modify,
# merge, publish, distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A
# PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
# HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
# SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
import os

import aws_cdk as cdk
from aws_cdk import CfnParameter
from aws_cdk import aws_iam as iam
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_sagemaker as sagemaker
from aws_cdk import aws_servicecatalog as servicecatalog
from aws_cdk import aws_ssm as ssm
from aws_cdk import custom_resources as cr
from constructs import Construct
from service_catalog.constructs.sagemaker_roles_construct import SagemakerRoles

BASE_DIR = os.path.dirname(os.path.realpath(__file__))


class SagemakerStudioDomain(servicecatalog.ProductStack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # CloudFormation parameters
        domain_name = CfnParameter(
            self,
            "StudioDomainName",
            type="String",
            description="Name to assign to the SageMaker Studio domain",
            default="studio-domain",
            allowed_pattern="^[a-zA-Z0-9](-*[a-zA-Z0-9]){0,62}",
        ).value_as_string

        environment = CfnParameter(
            self,
            "Environment",
            type="String",
            description="Environment for Sagemaker Domain",
            default="Dev",
        ).value_as_string

        finance_owner = CfnParameter(
            self,
            "FinanceOwner",
            type="String",
            description="Finance Owner for Sagemaker Domain",
            default="Workload-1-Development-team",
        ).value_as_string

        finance_bu = CfnParameter(
            self,
            "BusinessUnit",
            type="String",
            description="Finance Business Unit for Sagemaker Domain",
            default="Retail",
        ).value_as_string

        finance_cost_center = CfnParameter(
            self,
            "CostCenter",
            type="String",
            description="Cost Center for Sagemaker Domain",
            default="Retail-5045",
        ).value_as_string

        tags_list = [
            cdk.CfnTag(key="anycompany:workload:environment", value=environment),
            cdk.CfnTag(key="anycompany:finance:owner", value=finance_owner),
            cdk.CfnTag(key="anycompany:finance:business-unit", value=finance_bu),
            cdk.CfnTag(key="anycompany:finance:cost-center", value=finance_cost_center),
        ]

        # Interface for template parameters
        self.template_options.metadata = {
            "AWS::CloudFormation::Interface": {
                "ParameterGroups": [
                    {
                        "Label": {"default": "Tags"},
                        "Parameters": [
                            "Environment",
                            "FinanceOwner",
                            "BusinessUnit",
                            "CostCenter",
                        ],
                    },
                    {
                        "Label": {"default": "Sagemaker Parameters"},
                        "Parameters": [
                            "StudioDomainName",
                            "S3BucketName",
                            "SMProjectPortfolioId",
                        ],
                    },
                    {
                        "Label": {"default": "Infra Parameter Store"},
                        "Parameters": [
                            "SagemakerSgIdParameter",
                            "VpcIdParameter",
                            "PrivateSubnetsIdParameter",
                        ],
                    },
                ]
            }
        }

        # Import variables from parameter store
        vpc_id = ssm.StringParameter.from_string_parameter_name(
            self, id="VpcId", string_parameter_name="/vpc/id"
        ).string_value

        subnet_ids = ssm.StringListParameter.from_list_parameter_attributes(
            self, id="PrivateSubnetsId", parameter_name="/vpc/subnets/private/ids"
        ).string_list_value

        sagemaker_sg_id = ssm.StringParameter.from_string_parameter_name(
            self, id="SagemakerSgId", string_parameter_name="/vpc/sg/id"
        ).string_value

        # Roles for Sagemaker Profiles
        sagemaker_roles = SagemakerRoles(self, "SagemakerRoles", domain_name)

        # create sagemaker studio domain
        domain = sagemaker.CfnDomain(
            self,
            "sagemaker-domain",
            auth_mode="SSO",
            app_network_access_type="VpcOnly",
            default_user_settings=sagemaker.CfnDomain.UserSettingsProperty(
                execution_role=sagemaker_roles.sagemaker_studio_role.role_arn,
                security_groups=[sagemaker_sg_id],
                sharing_settings=sagemaker.CfnDomain.SharingSettingsProperty(),  # disable notebook output sharing
            ),
            domain_name=domain_name,
            subnet_ids=subnet_ids,
            vpc_id=vpc_id,
            tags=tags_list,
        )

        # create an S3 bucket and grant read/write privileges to all the roles associated with the domain
        studio_bucket = s3.Bucket(
            self,
            "DomainBucket",
            bucket_name=f"ml-{cdk.Aws.ACCOUNT_ID}-{domain.attr_domain_id}",
            enforce_ssl=True,
        )
        studio_bucket.grant_read_write(sagemaker_roles.data_scientist_role)
        studio_bucket.grant_read_write(sagemaker_roles.lead_data_scientist_role)
        studio_bucket.grant_read_write(sagemaker_roles.sagemaker_studio_role)

        # enable projects for the domain
        _ = cr.AwsCustomResource(
            self,
            "EnableSageMakerProjects",
            on_update=cr.AwsSdkCall(
                service="sagemaker",
                action="EnableSagemakerServicecatalogPortfolio",
                physical_resource_id=cr.PhysicalResourceId.of(id="ProjectsEnabled"),
            ),
            policy=cr.AwsCustomResourcePolicy.from_statements(
                [
                    iam.PolicyStatement(
                        effect=iam.Effect.ALLOW,
                        actions=[
                            "sagemaker:EnableSagemakerServicecatalogPortfolio",
                            "servicecatalog:ListAcceptedPortfolioShares",
                            "servicecatalog:AssociatePrincipalWithPortfolio",
                            "servicecatalog:AcceptPortfolioShare",
                            "iam:GetRole",
                        ],
                        resources=["*"],
                    ),
                ]
            ),
        )
