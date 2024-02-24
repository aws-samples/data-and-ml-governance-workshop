import aws_cdk as cdk
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as targets
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_ssm as ssm
from constructs import Construct


class ModelSyncConstruct(Construct):
    def __init__(
        self,
        scope: Construct,
        id: str,
        ml_central_event_bus: events.EventBus,
        ml_org_id: str,
        ml_deployment_org_path: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, id, **kwargs)

        # Bucket for all model artifacts in the central model registry
        model_artifacts_bucket = s3.Bucket(
            self,
            "ArtifactsBucket",
            encryption=s3.BucketEncryption.KMS,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            bucket_name=f"mlops-model-artifacts-{cdk.Aws.ACCOUNT_ID}-{cdk.Aws.REGION}",
            cors=[
                s3.CorsRule(
                    allowed_methods=[s3.HttpMethods.GET],
                    allowed_headers=["*"],
                    allowed_origins=["*"],
                    exposed_headers=[],
                )
            ],
        )

        sagemaker_domain_execution_role = iam.Role.from_role_arn(
            self,
            "SmExecutionRole",
            ssm.StringParameter.from_string_parameter_name(
                self,
                "SmExecutionRoleARN",
                string_parameter_name="/mlops/role/execution",
            ).string_value,
        )
        model_artifacts_bucket.grant_read_write(sagemaker_domain_execution_role)

        ## lambda function to sync models from dev accounts to ML central account
        powertools_layer = lambda_.LayerVersion.from_layer_version_arn(
            self,
            id="lambda-powertools",
            layer_version_arn=f"arn:aws:lambda:{cdk.Aws.REGION}:017000801446:layer:AWSLambdaPowertoolsPythonV2-Arm64:59",
        )

        sync_model_function = lambda_.Function(
            self,
            id="SyncModelFunction",
            code=lambda_.Code.from_asset("functions/model_sync"),
            handler="index.lambda_handler",
            runtime=lambda_.Runtime.PYTHON_3_12,
            architecture=lambda_.Architecture.ARM_64,
            layers=[powertools_layer],
            environment={
                "ArtifactBucketName": model_artifacts_bucket.bucket_name,
            },
            initial_policy=[
                iam.PolicyStatement(
                    actions=[
                        "sagemaker:DescribeModelPackage",
                        "sagemaker:DescribeModelPackageGroup",
                        "sagemaker:ListModelPackages",
                    ],
                    resources=[
                        f"arn:aws:sagemaker:{cdk.Aws.REGION}:*:model-package/*",
                        f"arn:aws:sagemaker:{cdk.Aws.REGION}:*:model-package-group/*",
                    ],
                ),
                iam.PolicyStatement(
                    actions=[
                        "sagemaker:CreateModelPackage",
                        "sagemaker:CreateModelPackageGroup",
                        "sagemaker:UpdateModelPackage",
                        "sagemaker:ListTags",
                    ],
                    resources=[
                        f"arn:aws:sagemaker:{cdk.Aws.REGION}:{cdk.Aws.ACCOUNT_ID}:model-package/*",
                        f"arn:aws:sagemaker:{cdk.Aws.REGION}:{cdk.Aws.ACCOUNT_ID}:model-package-group/*",
                    ],
                ),
                iam.PolicyStatement(
                    actions=[
                        "kms:Decrypt",
                        "kms:DescribeKey",
                        "kms:Encrypt",
                        "kms:GenerateDataKey*",
                        "kms:ReEncrypt*",
                        "s3:GetBucket*",
                        "s3:GetObject*",
                        "s3:List*",
                    ],
                    resources=["*"],
                    # TODO find out why the org condition doesn't work
                    # conditions={
                    #     "StringEquals": {
                    #         "aws:ResourceOrgID": ml_org_id,
                    #     }
                    # },
                ),
            ],
        )

        model_artifacts_bucket.grant_read_write(sync_model_function)

        # Policy for access from workload OU
        model_artifacts_bucket_policy = iam.PolicyStatement(
            actions=[
                "s3:Get*",
            ],
            resources=[
                model_artifacts_bucket.arn_for_objects("*"),
            ],
            principals=[iam.AnyPrincipal()],
            conditions={
                "ForAnyValue:StringLike": {
                    "aws:PrincipalOrgPaths": [ml_deployment_org_path]
                },
            },
        )
        model_artifacts_bucket.add_to_resource_policy(model_artifacts_bucket_policy)
        if (key := model_artifacts_bucket.encryption_key) is not None:
            key.add_to_resource_policy(
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
                    principals=[iam.AnyPrincipal()],
                    conditions={
                        "ForAnyValue:StringLike": {
                            "aws:PrincipalOrgPaths": [ml_deployment_org_path]
                        },
                    },
                )
            )

        # Rule to trigger the copy model Lambda Function
        events.Rule(  # noqa: F841
            self,
            "CopyEventBridgeRule",
            description="Trigger Synch Model Lambda function when source EventBridge event is received",
            enabled=True,
            event_pattern={
                "source": ["aws.sagemaker"],
                "detail_type": ["SageMaker Model Package State Change"],
                "detail": {
                    "ModelApprovalStatus": ["Approved"],
                },
            },
            targets=[
                targets.LambdaFunction(
                    handler=sync_model_function,  # type: ignore
                    # dead_letter_queue_enabled=True,
                    retry_attempts=2,
                )
            ],
            event_bus=ml_central_event_bus,
        )
