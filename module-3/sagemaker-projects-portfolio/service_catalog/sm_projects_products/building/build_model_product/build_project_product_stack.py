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

import aws_cdk
from aws_cdk import Aws, Tags
from aws_cdk import aws_codecommit as codecommit
from aws_cdk import aws_iam as iam
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_sagemaker as sagemaker
from aws_cdk import aws_servicecatalog as sc
from constructs import Construct
from service_catalog.sm_projects_products.building.constructs.build_pipeline_construct import (
    BuildPipelineConstruct,
)

BASE_DIR = os.path.dirname(os.path.realpath(__file__))


class MLOpsStack(sc.ProductStack):
    DESCRIPTION: str = (
        "This template includes creates a model building pipeline "
        "that includes a workflow to pre-process, train, "
        "evaluate and register a model."
    )
    TEMPLATE_NAME: str = (
        "Build only - MLOps template for model training and building SageMaker Pipeline."
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
        project_name = aws_cdk.CfnParameter(
            self,
            "SageMakerProjectName",
            type="String",
            description="The name of the SageMaker project.",
            allowed_pattern="^[a-zA-Z0-9](-*[a-zA-Z0-9]){0,31}",
        ).value_as_string

        project_id = aws_cdk.CfnParameter(
            self,
            "SageMakerProjectId",
            type="String",
            min_length=1,
            max_length=20,
            allowed_pattern="^[a-zA-Z0-9](-*[a-zA-Z0-9])*",
            description="Service generated Id of the project.",
        ).value_as_string

        tooling_account = os.getenv("CDK_DEFAULT_ACCOUNT")

        Tags.of(self).add("sagemaker:project-id", project_id)
        Tags.of(self).add("sagemaker:project-name", project_name)

        build_app_repository = codecommit.Repository(
            self,
            "BuildRepo",
            repository_name=f"sagemaker-{project_name}-{construct_id}",
            code=codecommit.Code.from_directory(
                directory_path=f"{BASE_DIR}/seed_code",
            ),
        )

        s3_artifact = s3.Bucket(
            self,
            "S3Artifact",
            bucket_name=f"sagemaker-{project_id}-{Aws.ACCOUNT_ID}",
            encryption=s3.BucketEncryption.KMS,
            versioned=False,
            removal_policy=aws_cdk.RemovalPolicy.DESTROY,
            enforce_ssl=True,
        )

        # Grant X-account access to the tooling account
        s3_artifact.grant_read(iam.AccountPrincipal(tooling_account))

        model_package_group_name = f"{project_name}-{project_id}"

        # cross account model registry resource policy
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
                        iam.AccountPrincipal(tooling_account),
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
                        iam.AccountPrincipal(tooling_account),
                    ], # type: ignore
                ),
            ]
        ).to_json()

        sagemaker.CfnModelPackageGroup(
            self,
            "ModelPackageGroup",
            model_package_group_name=model_package_group_name,
            model_package_group_description=f"Model Package Group for {project_name}",
            model_package_group_policy=model_package_group_policy,
            tags=[
                aws_cdk.CfnTag(key="sagemaker:project-id", value=project_id),
                aws_cdk.CfnTag(key="sagemaker:project-name", value=project_name),
            ],
        )

        pipeline_artifact_bucket = s3.Bucket(
            self,
            "PipelineBucket",
            bucket_name=f"pipeline-{project_id}-{Aws.ACCOUNT_ID}",
            encryption=s3.BucketEncryption.KMS,  # TODO: is a managed key a requirement for codebuild pipeline artifact bucket?
            versioned=True,
            removal_policy=aws_cdk.RemovalPolicy.DESTROY,
            enforce_ssl=True,
        )

        BuildPipelineConstruct(
            self,
            "build",
            project_name=project_name,
            project_id=project_id,
            pipeline_artifact_bucket=pipeline_artifact_bucket,
            model_package_group_name=model_package_group_name,
            repository=build_app_repository,
            s3_artifact=s3_artifact,
        )
