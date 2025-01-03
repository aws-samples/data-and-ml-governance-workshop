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
from aws_cdk import aws_iam as iam
from aws_cdk import aws_kms as kms
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_s3_deployment as s3deploy
from aws_cdk import aws_sagemaker as sagemaker
from aws_cdk import aws_servicecatalog as sc
from aws_cdk import aws_ssm as ssm
from constructs import Construct
from service_catalog.sm_projects_products.building.constructs.build_pipeline_construct import (
    BuildPipelineConstruct,
)

BASE_DIR = os.path.dirname(os.path.realpath(__file__))


class MLOpsStack(sc.ProductStack):
    DESCRIPTION: str = (
        "Use central feature store datasource - preprocess, train, register model build pipeline"
    )
    TEMPLATE_NAME: str = (
        "Bank marketing model - MLOps template to train model using Central Feature Store data"
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
            min_length=1,
            max_length=32,
        ).value_as_string

        project_id = aws_cdk.CfnParameter(
            self,
            "SageMakerProjectId",
            type="String",
            min_length=1,
            max_length=16,
            description="Service generated Id of the project.",
        ).value_as_string

        fg_name = aws_cdk.CfnParameter(
            self,
            "FeatureGroupName",
            type="String",
            min_length=1,
            max_length=50,
            description="Your central feature store feature group name for data prep",
        ).value_as_string

        owner = aws_cdk.CfnParameter(
            self,
            'RepoOwner',
            type='String',
            min_length=1,
            max_length=50,
            description='The owner or organization of your repository'
        ).value_as_string

        repository = aws_cdk.CfnParameter(
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

        tooling_account = os.getenv("CDK_DEFAULT_ACCOUNT")

        Tags.of(self).add("sagemaker:project-id", project_id)
        Tags.of(self).add("sagemaker:project-name", project_name)

        # create kms key to be used by the assets bucket
        kms_key = kms.Key(
            self,
            "ArtifactsBucketKMSKey",
            description="key used for encryption of data in Amazon S3",
            enable_key_rotation=True,
            policy=iam.PolicyDocument(
                statements=[
                    iam.PolicyStatement(
                        actions=["kms:*"],
                        effect=iam.Effect.ALLOW,
                        resources=["*"],
                        principals=[iam.AccountRootPrincipal()],  # type: ignore
                    )
                ]
            ),
        )

        # allow cross account access to the kms key
        kms_key.add_to_resource_policy(
            iam.PolicyStatement(
                actions=[
                    "kms:Encrypt",
                    "kms:Decrypt",
                    "kms:ReEncrypt*",
                    "kms:GenerateDataKey*",
                    "kms:DescribeKey",
                ],
                resources=[
                    "*",
                ],
                principals=[
                    iam.ArnPrincipal(f"arn:aws:iam::{tooling_account}:root"),
                ],  # type: ignore
            )
        )

        s3_artifact = s3.Bucket(
            self,
            "S3Artifact",
            bucket_name=f"mlops-{project_id}-{Aws.ACCOUNT_ID}",
            encryption_key=kms_key,  # type: ignore
            versioned=True,
            removal_policy=aws_cdk.RemovalPolicy.DESTROY,
            enforce_ssl=True,
        )

        # DEV account access to objects in the bucket
        s3_artifact.add_to_resource_policy(
            iam.PolicyStatement(
                sid="AddDevPermissions",
                actions=["s3:*"],
                resources=[
                    s3_artifact.arn_for_objects(key_pattern="*"),
                    s3_artifact.bucket_arn,
                ],
                principals=[
                    iam.ArnPrincipal(f"arn:aws:iam::{Aws.ACCOUNT_ID}:root"),
                ],  # type: ignore
            )
        )

        # PROD account access to objects in the bucket
        s3_artifact.add_to_resource_policy(
            iam.PolicyStatement(
                sid="AddCrossAccountPermissions",
                actions=["s3:List*", "s3:Get*", "s3:Put*"],
                resources=[
                    s3_artifact.arn_for_objects(key_pattern="*"),
                    s3_artifact.bucket_arn,
                ],
                principals=[
                    iam.ArnPrincipal(f"arn:aws:iam::{tooling_account}:root"),
                ],  # type: ignore
            )
        )

        deployment = s3deploy.BucketDeployment(self, 'DeploySeedcode',
                                  sources=[s3deploy.Source.asset(f'{BASE_DIR}/seed_code')],
                                  destination_bucket=s3_artifact,
                                  destination_key_prefix='seedcode',
                                  extract=False
        )

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
                        iam.ArnPrincipal(f"arn:aws:iam::{tooling_account}:root"),
                    ],  # type: ignore
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
                        iam.ArnPrincipal(f"arn:aws:iam::{tooling_account}:root"),
                    ],  # type: ignore
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

        kms_key = kms.Key(
            self,
            "PipelineBucketKMSKey",
            description="key used for encryption of data in Amazon S3",
            enable_key_rotation=True,
            policy=iam.PolicyDocument(
                statements=[
                    iam.PolicyStatement(
                        actions=["kms:*"],
                        effect=iam.Effect.ALLOW,
                        resources=["*"],
                        principals=[iam.AccountRootPrincipal()],  # type: ignore
                    )
                ]
            ),
        )

        pipeline_artifact_bucket = s3.Bucket(
            self,
            "PipelineBucket",
            bucket_name=f"pipeline-{project_id}-{Aws.ACCOUNT_ID}",
            encryption_key=kms_key,  # type: ignore
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
            owner=owner,
            repository=repository,
            connection_arn=connection_arn,
            s3_artifact=s3_artifact,
            deployment=deployment
        )
        # BuildPipelineConstruct(
        #     self,
        #     "build",
        #     project_name=project_name,
        #     project_id=project_id,
        #     pipeline_artifact_bucket=pipeline_artifact_bucket,
        #     model_package_group_name=model_package_group_name,
        #     repository=build_app_repository,
        #     s3_artifact=s3_artifact,
        #     build_env={"FeatureGroupName": fg_name},
        # )
