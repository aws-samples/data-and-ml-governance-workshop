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

from aws_cdk import aws_iam as iam
from constructs import Construct


class SagemakerRoles(Construct):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        # s3_bucket_prefix: str,
        domain_name: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # create policies required for the roles
        sm_deny_policy = iam.Policy(
            self,
            "sm-deny-policy",
            statements=[
                iam.PolicyStatement(
                    effect=iam.Effect.DENY,
                    actions=[
                        "sagemaker:CreateProject",
                    ],
                    resources=["*"],
                ),
                iam.PolicyStatement(
                    effect=iam.Effect.DENY,
                    actions=["sagemaker:UpdateModelPackage"],
                    resources=["*"],
                ),
            ],
        )

        services_policy = iam.Policy(
            self,
            "services-policy",
            statements=[
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=[
                        "lambda:Create*",
                        "lambda:Update*",
                        "lambda:Invoke*",
                    ],
                    resources=["*"],
                ),
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=[
                        "sagemaker:ListTags",
                    ],
                    resources=["*"],
                ),
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=[
                        "codeconnections:CreateConnection",
                        "codeconnections:UseConnection",
                        "codeconnections:GetConnection",
                        "codeconnections:ListConnections",
                        "codeconnections:ListInstallationTargets",
                        "codeconnections:GetInstallationUrl",
                        "codeconnections:GetIndividualAccessToken",
                        "codeconnections:StartOAuthHandshake",
                        "codeconnections:UpdateConnectionInstallation",
                        "codeconnections:ListTagsForResource"
                    ],
                    resources=["*"],
                ),
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=[
                        "ecr:BatchGetImage",
                        "ecr:BatchCheckLayerAvailability",
                        "ecr:GetDownloadUrlForLayer",
                        "ecr:GetRepositoryPolicy",
                        "ecr:DescribeRepositories",
                        "ecr:DescribeImages",
                        "ecr:ListImages",
                        "ecr:GetAuthorizationToken",
                        "ecr:GetLifecyclePolicy",
                        "ecr:GetLifecyclePolicyPreview",
                        "ecr:ListTagsForResource",
                        "ecr:DescribeImageScanFindings",
                        "ecr:CreateRepository",
                        "ecr:CompleteLayerUpload",
                        "ecr:UploadLayerPart",
                        "ecr:InitiateLayerUpload",
                        "ecr:PutImage",
                    ],
                    resources=["*"],
                ),
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=[
                        "servicecatalog:*",
                    ],
                    resources=["*"],
                ),
            ],
        )

        # TODO: reduce permission scope
        kms_policy = iam.Policy(
            self,
            "kms-policy",
            statements=[
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=[
                        "kms:CreateGrant",
                        "kms:Decrypt",
                        "kms:DescribeKey",
                        "kms:Encrypt",
                        "kms:ReEncrypt",
                        "kms:GenerateDataKey",
                    ],
                    resources=["*"],
                )
            ],
        )

        s3_policy = iam.Policy(
            self,
            "s3-policy",
            statements=[
                # iam.PolicyStatement(
                #     effect=iam.Effect.ALLOW,
                #     actions=[
                #         "s3:AbortMultipartUpload",
                #         "s3:DeleteObject",
                #         "s3:Describe*",
                #         "s3:GetObject",
                #         "s3:PutBucket*",
                #         "s3:PutObject",
                #         "s3:PutObjectAcl",
                #         "s3:GetBucketAcl",
                #         "s3:GetBucketLocation",
                #     ],
                #     resources=[
                #         "arn:aws:s3:::{}*/*".format(s3_bucket_prefix),
                #         "arn:aws:s3:::{}*".format(s3_bucket_prefix),
                #     ],
                # ),
                # iam.PolicyStatement(
                #     effect=iam.Effect.ALLOW,
                #     actions=["s3:ListBucket"],
                #     resources=["arn:aws:s3:::{}*".format(s3_bucket_prefix)],
                # ),
                iam.PolicyStatement(
                    effect=iam.Effect.DENY,
                    actions=["s3:DeleteBucket*"],
                    resources=["*"],
                ),
            ],
        )

        ## create role for each persona

        # role for Data Scientist persona
        self.data_scientist_role = iam.Role(
            self,
            "data-scientist-role",
            role_name="sagemaker-{}-data-scientist-role".format(domain_name),
            assumed_by=iam.CompositePrincipal(
                iam.ServicePrincipal(service="lambda.amazonaws.com"),
                iam.ServicePrincipal(service="sagemaker.amazonaws.com"),
            ),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AmazonSSMReadOnlyAccess"
                ),
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AWSLambda_ReadOnlyAccess"
                ),
                iam.ManagedPolicy.from_aws_managed_policy_name("AWSCodeCommitReadOnly"),
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AmazonEC2ContainerRegistryReadOnly"
                ),
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AmazonSageMakerFullAccess"
                ),
            ],
        )

        self.data_scientist_role.attach_inline_policy(sm_deny_policy)
        self.data_scientist_role.attach_inline_policy(services_policy)
        self.data_scientist_role.attach_inline_policy(kms_policy)
        self.data_scientist_role.attach_inline_policy(s3_policy)

        # role for Lead Data Scientist persona
        self.lead_data_scientist_role = iam.Role(
            self,
            "lead-data-scientist-role",
            role_name="sagemaker-{}-lead-data-scientist-role".format(domain_name),
            assumed_by=iam.CompositePrincipal(
                iam.ServicePrincipal("lambda.amazonaws.com"),
                iam.ServicePrincipal("sagemaker.amazonaws.com"),
            ),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AmazonSSMReadOnlyAccess"
                ),
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AWSLambda_ReadOnlyAccess"
                ),
                iam.ManagedPolicy.from_aws_managed_policy_name("AWSCodeCommitReadOnly"),
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AmazonEC2ContainerRegistryReadOnly"
                ),
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AmazonSageMakerFullAccess"
                ),
            ],
        )

        self.lead_data_scientist_role.attach_inline_policy(services_policy)
        self.lead_data_scientist_role.attach_inline_policy(kms_policy)
        self.lead_data_scientist_role.attach_inline_policy(s3_policy)

        # default role for sagemaker persona
        self.sagemaker_studio_role = iam.Role(
            self,
            "sagemaker-studio-role",
            role_name="sagemaker-{}-execution-role".format(domain_name),
            assumed_by=iam.CompositePrincipal(
                iam.ServicePrincipal("lambda.amazonaws.com"),
                iam.ServicePrincipal("sagemaker.amazonaws.com"),
            ),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AmazonSSMReadOnlyAccess"
                ),
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AWSLambda_ReadOnlyAccess"
                ),
                iam.ManagedPolicy.from_aws_managed_policy_name("AWSCodeCommitReadOnly"),
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AmazonEC2ContainerRegistryReadOnly"
                ),
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AmazonSageMakerFullAccess"
                ),
            ],
        )

        self.sagemaker_studio_role.attach_inline_policy(services_policy)
        self.sagemaker_studio_role.attach_inline_policy(kms_policy)
        self.sagemaker_studio_role.attach_inline_policy(s3_policy)