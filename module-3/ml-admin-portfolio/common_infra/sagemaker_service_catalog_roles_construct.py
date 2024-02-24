import aws_cdk as cdk
import aws_cdk.aws_iam as iam
from constructs import Construct


class SageMakerSCRoles(Construct):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        pipeline_bucket_prefix: str,
        mutable: bool = True,
        **kwargs,
    ):
        super().__init__(scope, construct_id, **kwargs)

        s3_broad_policies = [
            iam.PolicyStatement(
                actions=[
                    "s3:ListAccessPointsForObjectLambda",
                    "s3:GetAccessPoint",
                    "s3:PutAccountPublicAccessBlock",
                    "s3:ListAccessPoints",
                    "s3:CreateStorageLensGroup",
                    "s3:ListJobs",
                    "s3:PutStorageLensConfiguration",
                    "s3:ListMultiRegionAccessPoints",
                    "s3:ListStorageLensGroups",
                    "s3:ListStorageLensConfigurations",
                    "s3:GetAccountPublicAccessBlock",
                    "s3:ListAllMyBuckets",
                    "s3:ListAccessGrantsInstances",
                    "s3:PutAccessPointPublicAccessBlock",
                    "s3:CreateJob",
                ],
                resources=["*"],
            ),
            iam.PolicyStatement(
                actions=["s3:*"],
                resources=[
                    f"arn:aws:s3:::{pipeline_bucket_prefix}*/*",
                    f"arn:aws:s3:::{pipeline_bucket_prefix}*",
                ],  # TODO: reduce scope of permissions,
            ),
        ]

        self.api_gw_role = iam.Role(
            self,
            "SMProductsApiGatewayRole",
            assumed_by=iam.ServicePrincipal("apigateway.amazonaws.com"),
            role_name="MLOpsServiceCatalogProductsApiGatewayServiceRole",
            description="Role created by ML Central account. This role will grant permissions required to use AWS ApiGateway within the Amazon SageMaker portfolio of products.",
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AmazonSageMakerServiceCatalogProductsApiGatewayServiceRolePolicy"
                )
            ],
            max_session_duration=cdk.Duration.hours(1),
        )

        self.cloudformation_role = iam.Role(
            self,
            "SMProductsCloudformationRole",
            assumed_by=iam.ServicePrincipal("cloudformation.amazonaws.com"),
            role_name="MLOpsServiceCatalogProductsCloudFormationRole",
            description="Role created by ML Central account. This role will grant permissions required to use AWS CloudFormation within the Amazon SageMaker portfolio of products.",
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AmazonSageMakerServiceCatalogProductsCloudformationServiceRolePolicy"
                )
            ],
            max_session_duration=cdk.Duration.hours(1),
        )

        self.code_build_role = iam.Role(
            self,
            "SMProductsCodeBuildRole",
            assumed_by=iam.ServicePrincipal("codebuild.amazonaws.com"),
            role_name="MLOpsServiceCatalogProductsCodeBuildRole",
            description="Role created by ML Central account. This role will grant permissions required to use AWS CodeBuild within the Amazon SageMaker portfolio of products.",
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AmazonSageMakerServiceCatalogProductsCodeBuildServiceRolePolicy"
                )
            ],
            inline_policies={
                "MLOps": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            actions=["iam:PassRole"],
                            resources=[
                                "arn:aws:iam::*:role/MLOpsServiceCatalogProductsEventsRole",
                                "arn:aws:iam::*:role/MLOpsServiceCatalogProductsCodePipelineRole",
                                "arn:aws:iam::*:role/MLOpsServiceCatalogProductsCloudformationRole",
                                "arn:aws:iam::*:role/MLOpsServiceCatalogProductsCodeBuildRole",
                                "arn:aws:iam::*:role/MLOpsServiceCatalogProductsExecutionRole",
                            ],
                            conditions={
                                "StringEquals": {
                                    "iam:PassedToService": [
                                        "events.amazonaws.com",
                                        "codepipeline.amazonaws.com",
                                        "cloudformation.amazonaws.com",
                                        "codebuild.amazonaws.com",
                                        "sagemaker.amazonaws.com",
                                    ]
                                }
                            },
                        ),
                        iam.PolicyStatement(
                            actions=[
                                "kms:Decrypt",
                                "kms:Encrypt",
                                "kms:GenerateDataKey",
                                "sagemaker:DescribeImageVersion",
                                "kms:DescribeKey",
                            ],
                            resources=[
                                f"arn:aws:kms:*:{cdk.Aws.ACCOUNT_ID}:key/*",  # TODO: reduce scope of permissions, possibly using tags
                                "arn:aws:sagemaker:*:*:image-version/*/*",
                            ],
                        ),
                        *s3_broad_policies,
                    ]
                ),
            },
            max_session_duration=cdk.Duration.hours(1),
        )

        self.code_pipeline_role = iam.Role(
            self,
            "SMProductsCodePipelineRole",
            assumed_by=iam.ServicePrincipal("codepipeline.amazonaws.com"),
            role_name="MLOpsServiceCatalogProductsCodePipelineRole",
            description="Role created by ML Central account. This role will grant permissions required to use AWS CodePipeline within the Amazon SageMaker portfolio of products.",
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AmazonSageMakerServiceCatalogProductsCodePipelineServiceRolePolicy"
                )
            ],
            max_session_duration=cdk.Duration.hours(1),
            inline_policies={
                "MLOps": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            actions=["iam:PassRole"],
                            resources=[
                                "arn:aws:iam::*:role/MLOpsServiceCatalogProductsCloudformationRole",
                            ],
                        ),
                        iam.PolicyStatement(
                            actions=[
                                "sts:AssumeRole",
                                "kms:Decrypt",
                                "kms:Encrypt",
                                "codepipeline:CreatePipeline",
                                "kms:GenerateDataKey",
                                "kms:DescribeKey",
                            ],
                            resources=[
                                f"arn:aws:kms:*:{cdk.Aws.ACCOUNT_ID}:key/*",
                                f"arn:aws:iam::{cdk.Aws.ACCOUNT_ID}:role/MLOpsServiceCatalog*",
                                f"arn:aws:codepipeline:*:{cdk.Aws.ACCOUNT_ID}:*",
                            ],
                        ),
                        *s3_broad_policies,
                    ]
                )
            },
        )

        self.events_role = iam.Role(
            self,
            "SMProductsEventsRole",
            assumed_by=iam.ServicePrincipal("events.amazonaws.com"),
            role_name="MLOpsServiceCatalogProductsEventsRole",
            description="Role created by ML Central account. This role will grant permissions required to use AWS Events within the Amazon SageMaker portfolio of products.",
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AmazonSageMakerServiceCatalogProductsEventsServiceRolePolicy"
                )
            ],
            max_session_duration=cdk.Duration.hours(1),
        )

        self.execution_role = iam.Role(  # TODO: replace with smaller permission scope
            self,
            "SMProductsExecutionRole",
            assumed_by=iam.ServicePrincipal("sagemaker.amazonaws.com"),
            role_name="MLOpsServiceCatalogProductsExecutionRole",
            description="Role created by ML Central account. This role will grant permissions required to use AWS SageMaker within the Amazon SageMaker portfolio of products.",
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AmazonSageMakerFullAccess"
                )
            ],
            inline_policies={
                "MLOps": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            actions=[
                                "kms:Decrypt",
                                "kms:Encrypt",
                                "kms:GenerateDataKey",
                            ],
                            resources=[
                                f"arn:aws:kms:*:{cdk.Aws.ACCOUNT_ID}:key/*"
                            ],  # TODO: reduce scope of permissions, possibly using tags
                        )
                    ]
                )
            },
            max_session_duration=cdk.Duration.hours(1),
        )

        self.firehose_role = iam.Role(
            self,
            "SMProductsFirehoseRole",
            assumed_by=iam.ServicePrincipal("firehose.amazonaws.com"),
            role_name="MLOpsServiceCatalogProductsFirehoseRole",
            description="Role created by ML Central account. This role will grant permissions required to use AWS Firehose within the Amazon SageMaker portfolio of products.",
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AmazonSageMakerServiceCatalogProductsFirehoseServiceRolePolicy"
                )
            ],
            max_session_duration=cdk.Duration.hours(1),
        )

        self.glue_role = iam.Role(
            self,
            "SMProductsGlueRole",
            assumed_by=iam.ServicePrincipal("glue.amazonaws.com"),
            role_name="MLOpsServiceCatalogProductsGlueRole",
            description="Role created by ML Central account. This role will grant permissions required to use AWS Glue within the Amazon SageMaker portfolio of products.",
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AmazonSageMakerServiceCatalogProductsGlueServiceRolePolicy"
                )
            ],
            max_session_duration=cdk.Duration.hours(1),
        )

        self.lambda_role = iam.Role(
            self,
            "SMProductsLambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            role_name="MLOpsServiceCatalogProductsLambdaRole",
            description="Role created by XX Central account. This role will grant permissions required to use AWS Lambda within the Amazon SageMaker portfolio of products.",
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AmazonSageMakerServiceCatalogProductsLambdaServiceRolePolicy"
                )
            ],
            max_session_duration=cdk.Duration.hours(1),
        )

        self.launch_role = iam.Role(
            self,
            "SMProductsLaunchRole",
            assumed_by=iam.ServicePrincipal("servicecatalog.amazonaws.com"),
            role_name="MLOpsServiceCatalogProductsLaunchRole",
            description="Role created by ML Central account. This role has the permissions required to launch the Amazon SageMaker portfolio of products from AWS ServiceCatalog.",
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AmazonSageMakerAdmin-ServiceCatalogProductsServiceRolePolicy"
                ),
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AmazonS3FullAccess"
                ),  # TODO: restrict scope
            ],
            inline_policies={
                "MLOps": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            actions=["sagemaker:AddTags"],
                            resources=["*"],
                        ),
                        iam.PolicyStatement(
                            actions=[
                                "kms:Encrypt",
                                "kms:ReEncrypt*",
                                "kms:GenerateDataKey*",
                                "kms:Decrypt",
                                "kms:DescribeKey",
                                "kms:EnableKeyRotation",
                                "kms:ListKeys",
                            ],
                            resources=[
                                f"arn:aws:kms:{cdk.Aws.REGION}:{cdk.Aws.ACCOUNT_ID}:key/*"
                            ],
                        ),
                        iam.PolicyStatement(
                            actions=[
                                "kms:TagResource",
                                "kms:CreateKey",
                                "kms:PutKeyPolicy",
                            ],
                            resources=["*"],
                        ),
                        # *s3_broad_policies,  # not sufficient
                        iam.PolicyStatement(
                            actions=[
                                "sagemaker:DeleteTags",
                                "sagemaker:ListTags",
                                "sagemaker:DeleteModelPackageGroupPolicy",
                                "sagemaker:PutModelPackageGroupPolicy",
                                "sagemaker:GetModelPackageGroupPolicy",
                                "sagemaker:DeleteModelPackageGroup",
                                "sagemaker:DescribeModelPackageGroup",
                                "sagemaker:CreateModelPackageGroup",
                                "sagemaker:AddTags",
                            ],
                            resources=[
                                f"arn:aws:sagemaker:{cdk.Aws.REGION}:{cdk.Aws.ACCOUNT_ID}:model-package-group/*"
                            ],
                        ),
                        iam.PolicyStatement(
                            actions=["iam:PassRole"],
                            resources=[
                                f"arn:aws:iam::{cdk.Aws.ACCOUNT_ID}:role/MLOpsServiceCatalogProducts*"
                            ],
                        ),
                        iam.PolicyStatement(
                            actions=["events:DescribeRule"],
                            resources=[
                                f"arn:aws:events:{cdk.Aws.REGION}:{cdk.Aws.ACCOUNT_ID}:rule/*"
                            ],
                        ),
                        iam.PolicyStatement(
                            actions=[
                                "events:DescribeRule",
                                "events:PutRule",
                                "events:TagResource",
                                "events:DeleteRule",
                                "events:PutTargets",
                                "events:RemoveTargets",
                                "events:UntagResource",
                            ],
                            resources=[
                                f"arn:aws:events:*:{cdk.Aws.ACCOUNT_ID}:rule/*",
                                f"arn:aws:events:*:{cdk.Aws.ACCOUNT_ID}:event-bus/*",
                            ],
                        ),
                    ]
                )
            },
            max_session_duration=cdk.Duration.hours(1),
        )

        self.use_role = iam.Role(
            self,
            "SMProductsUseRole",
            assumed_by=iam.CompositePrincipal(
                *[
                    iam.ServicePrincipal(k)
                    for k in [
                        "apigateway.amazonaws.com",
                        "cloudformation.amazonaws.com",
                        "states.amazonaws.com",
                        "events.amazonaws.com",
                        "sagemaker.amazonaws.com",
                        "lambda.amazonaws.com",
                        "glue.amazonaws.com",
                        "codebuild.amazonaws.com",
                        "firehose.amazonaws.com",
                        "codepipeline.amazonaws.com",
                    ]
                ]
            ),
            role_name="MLOpsServiceCatalogProductsUseRole",
            description="Role created by ML Central account. This role has the permissions required to launch the Amazon SageMaker portfolio of products from AWS ServiceCatalog.",
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AmazonSageMakerAdmin-ServiceCatalogProductsServiceRolePolicy"
                )
            ],
            max_session_duration=cdk.Duration.hours(1),
        )
