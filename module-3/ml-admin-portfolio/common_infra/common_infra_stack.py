import os
import subprocess

import aws_cdk as cdk
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as targets
from aws_cdk import aws_iam as iam
from aws_cdk import aws_ssm as ssm
from aws_cdk import cloudformation_include as cfn_inc
from cdk_stacksets import (
    Capability,
    DeploymentType,
    StackSet,
    StackSetStack,
    StackSetTarget,
    StackSetTemplate,
)
from common_infra.model_sync_construct import ModelSyncConstruct
from common_infra.sagemaker_service_catalog_roles_construct import SageMakerSCRoles
from constructs import Construct

central_account_id = os.getenv("CDK_DEFAULT_ACCOUNT", cdk.Aws.ACCOUNT_ID)
region = os.getenv("CDK_DEFAULT_REGION", cdk.Aws.REGION)


class Bootstrap(StackSetStack):
    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        template_file_name = "bootstrap-template.json"

        with open(template_file_name, "w") as f:
            subprocess.run(
                [
                    "cdk",
                    "bootstrap",
                    "--show-template",
                    "-j",
                ],
                stdout=f,
            )

        _ = cfn_inc.CfnInclude(
            self,
            "Template",
            template_file=template_file_name,
        )


class DevSpokeInfra(StackSetStack):
    def __init__(
        self, scope: Construct, construct_id: str, target_event_bus_arn: str, **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        ssm.StringParameter(
            self,
            "MlCentralAccountId",
            parameter_name="ml-central-account-id",
            string_value=central_account_id,
        )

        events.Rule(
            self,
            "RegisteredModelApproved",
            description="Create event in ML central services account when a registered model is approved.",
            event_pattern=events.EventPattern(
                source=["aws.sagemaker"],
                detail_type=["SageMaker Model Package State Change"],
                detail={
                    "ModelApprovalStatus": ["Approved"],
                    # "ModelPackageGroupName": ["*"],
                },
            ),
            targets=[
                targets.EventBus(
                    events.EventBus.from_event_bus_arn(
                        self,
                        "External",
                        target_event_bus_arn,
                    )
                )
            ],
        )

        # Roles for Sagemaker Projects
        _ = SageMakerSCRoles(
            self, "SagemakerScRoles", pipeline_bucket_prefix="pipeline"
        )

        ## TODO: Needs to debug the rule pattern
        # powertools_layer = lambda_.LayerVersion.from_layer_version_arn(
        #     self,
        #     "PowertoolsLayer",
        #     layer_version_arn=f"arn:aws:lambda:{cdk.Aws.REGION}:017000801446:layer:AWSLambdaPowertoolsPythonV2-Arm64:58",
        # )

        # with open(
        #     "service_catalog/ml_admin_products/functions/model_package_group_policy/index.py",
        #     encoding="utf8",
        # ) as fp:
        #     handler_code = fp.read()

        # model_pkg_policy_fn = lambda_.Function(
        #     self,
        #     "CrossAccountModelPackageGroupFunction",
        #     code=lambda_.Code.from_inline(handler_code),
        #     handler="index.handler",
        #     timeout=cdk.Duration.minutes(1),
        #     runtime=lambda_.Runtime.PYTHON_3_12,
        #     architecture=lambda_.Architecture.ARM_64,
        #     layers=[powertools_layer],
        #     initial_policy=[
        #         iam.PolicyStatement(actions=["sagemaker:*"], resources=["*"])
        #     ],  # TODO restrict access
        #     environment={"CENTRAL_ACCOUNT_ID": central_account_id},
        # )

        # events.Rule(
        #     self,
        #     "ModelPackageGroupCreated",
        #     description="Create event in ML central services account when a registered model is approved.",
        #     event_pattern=events.EventPattern(
        #         source=["aws.cloudtrail"],
        #         detail_type=["AWS API Call via CloudTrail"],
        #         detail={
        #             "eventSource": ["sagemaker.amazonaws.com"],
        #             "eventName": ["CreateModelPackageGroup"],
        #         },
        #     ),
        #     targets=[targets.LambdaFunction(model_pkg_policy_fn)],  # type: ignore
        # )


# TODO: class DeploySpokeInfra(StackSetStack):
# role assumed by CodePipeline in central account for CFN deployment


class CommonInfraStack(cdk.Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        ml_org_id: str,
        ml_deployment_org_id: str,
        ml_deployment_org_path: str,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Central event bus
        ml_central_event_bus_name = "ml-central-event-bus"
        ml_central_event_bus = events.EventBus(
            self, "MlCentralEventBus", event_bus_name=ml_central_event_bus_name
        )

        ml_central_event_bus.add_to_resource_policy(
            iam.PolicyStatement(
                sid="OrganizationPutEvents",
                actions=["events:PutEvents"],
                principals=[iam.AnyPrincipal()],
                resources=[ml_central_event_bus.event_bus_arn],
                conditions={"StringEquals": {"aws:PrincipalOrgID": ml_org_id}},
            )
        )

        # Roles for Sagemaker Projects
        _ = SageMakerSCRoles(
            self, "SagemakerScRoles", pipeline_bucket_prefix="pipeline"
        )

        ModelSyncConstruct(
            self,
            "ModelSync",
            ml_org_id=ml_org_id,
            ml_deployment_org_path=ml_deployment_org_path,
            ml_central_event_bus=ml_central_event_bus,
        )

        # Create stacksets
        _ = StackSet(
            self,
            "StackSetCentralModelRegistry",
            stack_set_name="MLOpsCentralModelRegistryBus",
            description="Parameters and rules to implement a centralized model registry",
            template=StackSetTemplate.from_stack_set_stack(
                DevSpokeInfra(
                    scope=self,
                    construct_id="CentralModelRegistryBus",
                    target_event_bus_arn=self.format_arn(
                        account=central_account_id,
                        region=region,
                        resource="event-bus",
                        service="events",
                        resource_name=ml_central_event_bus_name,
                        arn_format=cdk.ArnFormat.SLASH_RESOURCE_NAME,
                    ),
                )
            ),
            target=StackSetTarget.from_organizational_units(
                regions=[region], organizational_units=[ml_org_id]
            ),
            deployment_type=DeploymentType.service_managed(
                auto_deploy_enabled=True,
                auto_deploy_retain_stacks=False,
                delegated_admin=True,
            ),
            capabilities=[Capability.NAMED_IAM],
        )

        _ = StackSet(
            self,
            "CDKBootstrapStackSet",
            stack_set_name="CDKBootstrap",
            template=StackSetTemplate.from_stack_set_stack(
                Bootstrap(scope=self, id="CDKBootstrap"),
            ),
            target=StackSetTarget.from_organizational_units(
                regions=[region],
                organizational_units=[ml_deployment_org_id],
                exclude_accounts=[central_account_id],
                parameter_overrides={
                    "TrustedAccounts": ",".join([central_account_id]),
                    "CloudFormationExecutionPolicies": "arn:aws:iam::aws:policy/AdministratorAccess", #TODO: reduce scope of CFN deployment role in spoke account
                },
            ),
            deployment_type=DeploymentType.service_managed(auto_deploy_enabled=True),
            capabilities=[Capability.NAMED_IAM],
        )
