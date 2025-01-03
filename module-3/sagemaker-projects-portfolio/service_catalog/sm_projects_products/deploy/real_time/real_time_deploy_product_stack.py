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

import json
import os

import aws_cdk as cdk
import aws_cdk.aws_servicecatalog as sc
from aws_cdk import Aws, CfnParameter, Tags
from aws_cdk import aws_iam as iam
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_s3_deployment as s3deploy
from aws_cdk import aws_ssm as ssm
from aws_cdk import custom_resources as cr
from constructs import Construct
from service_catalog.sm_projects_products.deploy.constructs.deploy_pipeline_construct import (
    DeployPipelineConstruct,
)
from service_catalog.sm_projects_products.deploy.constructs.ssm_construct import SSMConstruct

BASE_DIR = os.path.dirname(os.path.realpath(__file__))


class MLOpsStack(sc.ProductStack):
    DESCRIPTION: str = (
        "This template deploys a SageMaker endpoint cross-account from "
        "a pre-existing SageModel Registry using a AWS CodePipeline for deployment. "
        "The deploy pipeline creates preprod "
        "and production endpoint as infrastructure as code. The PREPROD/PROD accounts "
        "need to be cdk bootstrapped in advance to have the right CloudFormation "
        "execution cross account roles. The SageMaker Model Registry and associated ecr"
        " and s3 artifacts need to have the right cross account policies."
    )

    TEMPLATE_NAME: str = (
        "Deploy real-time endpoint from ModelRegistry - Cross account, test and prod"
    )

    @classmethod
    def get_description(cls) -> str:
        return cls.DESCRIPTION

    @classmethod
    def get_template_name(cls) -> str:
        return cls.TEMPLATE_NAME

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        asset_bucket: s3.Bucket | None = None,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, asset_bucket=asset_bucket, **kwargs)

        # Define required parameters
        project_name = cdk.CfnParameter(
            self,
            "SageMakerProjectName",
            type="String",
            description="The name of the Deployment SageMaker project.",
            allowed_pattern="^[a-zA-Z0-9](-*[a-zA-Z0-9]){0,31}",
        ).value_as_string

        project_id = cdk.CfnParameter(
            self,
            "SageMakerProjectId",
            type="String",
            min_length=1,
            max_length=20,
            allowed_pattern="^[a-zA-Z0-9](-*[a-zA-Z0-9])*",
            description="Service generated Id of the project.",
        ).value_as_string

        preprod_account = cdk.CfnParameter(
            self,
            "PreProdAccount",
            type="String",
            description="Id of preprod account.",
            allowed_pattern="^\\d{12}$",
        ).value_as_string

        prod_account = cdk.CfnParameter(
            self,
            "ProdAccount",
            type="String",
            allowed_pattern="^\\d{12}$",
            description="Id of prod account.",
        ).value_as_string

        owner = cdk.CfnParameter(
            self,
            'RepoOwner',
            type='String',
            min_length=1,
            max_length=50,
            description='The owner or organization of your repository'
        ).value_as_string

        repository = cdk.CfnParameter(
            self,
            'Repo',
            type='String',
            min_length=1,
            max_length=100,
            description='The name of your repository'
        ).value_as_string

        connection_arn = ssm.StringParameter.from_string_parameter_name(
            self, id="CodeConnectionArn", string_parameter_name="/codeconnection/arn"
        ).string_value

        # x-region support postponed to alter iteration
        # deployment_region = cdk.CfnParameter(
        #     self,
        #     "DeploymentRegion",
        #     type="String",
        #     min_length=8,
        #     max_length=10,
        #     description="Deployment region for preprod and prod account.",
        # ).value_as_string

        model_package_group_name = CfnParameter(
            self,
            "SageMakerModelPackageGroupName",
            type="String",
            description="The name of the SageMaker Model Package Group used to deploy endpoints",
            min_length=1,
            max_length=63,
            allowed_pattern="^[a-zA-Z0-9](-*[a-zA-Z0-9])*$",
        ).value_as_string

        Tags.of(self).add("sagemaker:project-id", project_id)
        Tags.of(self).add("sagemaker:project-name", project_name)

        SSMConstruct(
            self,
            "MLOpsSSM",
            project_name=project_name,
            preprod_account=preprod_account,
            prod_account=prod_account,
            deployment_region=cdk.Aws.REGION,  # Modify when x-region is enabled
        )

        # Pipeline artifact bucket with X-account resource policies
        pipeline_artifact_bucket = s3.Bucket(
            self,
            "PipelineBucket",
            bucket_name=f"pipeline-{project_id}-{Aws.ACCOUNT_ID}",
            versioned=False,
            encryption=s3.BucketEncryption.KMS,
            removal_policy=cdk.RemovalPolicy.DESTROY,
            enforce_ssl=True,
        )
        pipeline_artifact_bucket.grant_read(
            identity=iam.AccountPrincipal(preprod_account)
        )
        pipeline_artifact_bucket.grant_read(identity=iam.AccountPrincipal(prod_account))

        deployment = s3deploy.BucketDeployment(self, 'DeploySeedcode',
                                  sources=[s3deploy.Source.asset(f'{BASE_DIR}/seed_code')],
                                  destination_bucket=pipeline_artifact_bucket,
                                  destination_key_prefix='seedcode',
                                  extract=False
        )

        ## Added from central_model_registry stack
        model_package_group_policy = iam.PolicyDocument(
            statements=[
                iam.PolicyStatement(
                    sid="ModelPackageGroup",
                    actions=[
                        "sagemaker:DescribeModelPackageGroup",
                    ],
                    resources=[
                        f"arn:aws:sagemaker:{Aws.REGION}:{Aws.ACCOUNT_ID}:model-package-group/{model_package_group_name}"
                    ],
                    principals=[
                        iam.ArnPrincipal(f"arn:aws:iam::{preprod_account}:root"),
                        iam.ArnPrincipal(f"arn:aws:iam::{prod_account}:root"),
                    ], # type: ignore
                ),
                iam.PolicyStatement(
                    sid="ModelPackage",
                    actions=[
                        "sagemaker:DescribeModelPackage",
                        "sagemaker:ListModelPackages",
                        "sagemaker:UpdateModelPackage",
                        "sagemaker:CreateModel",
                    ],
                    resources=[
                        f"arn:aws:sagemaker:{Aws.REGION}:{Aws.ACCOUNT_ID}:model-package/{model_package_group_name}/*"
                    ],
                    principals=[
                        iam.ArnPrincipal(f"arn:aws:iam::{preprod_account}:root"),
                        iam.ArnPrincipal(f"arn:aws:iam::{prod_account}:root"),
                    ], # type: ignore
                ),
            ]
        ).to_json()

        model_package_group_policy = json.dumps(model_package_group_policy)

        ## Attach cross account policy to pre-existing central Model Registry using cdk/Cfn custom resource
        _ = cr.AwsCustomResource(
            self,
            "AttachModelCrossAccountPolicy",
            on_update=cr.AwsSdkCall(
                service="sagemaker",
                action="PutModelPackageGroupPolicy",
                parameters={
                    "ModelPackageGroupName": model_package_group_name,
                    "ResourcePolicy": model_package_group_policy,
                },
                physical_resource_id=cr.PhysicalResourceId.of(id="XAccPolicyCreated"),
            ),
            policy=cr.AwsCustomResourcePolicy.from_sdk_calls(
                resources=cr.AwsCustomResourcePolicy.ANY_RESOURCE,
            ),
        )

        ## Adding project tags to models in ModelRegistry to include them into the project panel
        _ = cr.AwsCustomResource(
            self,
            "AddProjectTagsToModelPackageGroup",
            on_update=cr.AwsSdkCall(
                service="sagemaker",
                action="AddTags",
                parameters={
                    "ResourceArn": f"arn:aws:sagemaker:{cdk.Aws.REGION}:{cdk.Aws.ACCOUNT_ID}:model-package-group/{model_package_group_name}",
                    "Tags": [
                        {"Key": "sagemaker:project-id", "Value": project_id},
                        {"Key": "sagemaker:project-name", "Value": project_name},
                    ],
                },
                physical_resource_id=cr.PhysicalResourceId.of(
                    id="ModelPackageGroupTags"
                ),
            ),
            policy=cr.AwsCustomResourcePolicy.from_sdk_calls(
                resources=cr.AwsCustomResourcePolicy.ANY_RESOURCE,
            ),
        )

        DeployPipelineConstruct(
            self,
            "deploy",
            project_name=project_name,
            project_id=project_id,
            pipeline_artifact_bucket=pipeline_artifact_bucket,
            model_package_group_name=model_package_group_name,
            owner=owner,
            repository=repository,
            connection_arn=connection_arn,
            preprod_account=preprod_account,
            prod_account=prod_account,
            deployment_region=cdk.Aws.REGION,
            create_model_event_rule=True,
            deployment=deployment
        )
