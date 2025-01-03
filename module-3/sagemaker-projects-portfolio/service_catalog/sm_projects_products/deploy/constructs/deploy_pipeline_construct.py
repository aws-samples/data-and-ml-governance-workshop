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

import aws_cdk
from aws_cdk import Aws, CfnCapabilities
from aws_cdk import aws_codebuild as codebuild
from aws_cdk import aws_codepipeline as codepipeline
from aws_cdk import aws_codepipeline_actions as codepipeline_actions
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as targets
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_s3_deployment as s3deploy
from aws_cdk import aws_sagemaker as sagemaker
from aws_cdk import Fn
from constructs import Construct


class DeployPipelineConstruct(Construct):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        project_name: str,
        project_id: str,
        pipeline_artifact_bucket: s3.Bucket,
        model_package_group_name: str,
        owner: str,
        repository: str,
        connection_arn: str,
        preprod_account: str,
        prod_account: str,
        deployment_region: str,
        create_model_event_rule: bool,
        deployment: s3deploy.BucketDeployment ,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Define resource names
        pipeline_name = f"sagemaker-{project_name}-{construct_id}"

        cdk_synth_build_role = iam.Role(
            self,
            "CodeBuildRole",
            assumed_by=iam.ServicePrincipal("codebuild.amazonaws.com"),
            path="/service-role/",
        )

        cdk_synth_build_role.add_to_policy(
            iam.PolicyStatement(
                actions=["sagemaker:ListModelPackages"],
                resources=[
                    f"arn:{Aws.PARTITION}:sagemaker:{Aws.REGION}:{Aws.ACCOUNT_ID}:model-package-group/*",  # TODO: Add conditions
                    f"arn:{Aws.PARTITION}:sagemaker:{Aws.REGION}:{Aws.ACCOUNT_ID}:model-package/*",  # TODO: Add conditions
                ],
            )
        )

        cdk_synth_build_role.add_to_policy(
            iam.PolicyStatement(
                actions=["ssm:GetParameter"],
                resources=[
                    f"arn:{Aws.PARTITION}:ssm:{Aws.REGION}:{Aws.ACCOUNT_ID}:parameter/*",
                ],
            )
        )

        cdk_synth_build_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "kms:Encrypt",
                    "kms:ReEncrypt*",
                    "kms:GenerateDataKey*",
                    "kms:Decrypt",
                    "kms:DescribeKey",
                ],
                effect=iam.Effect.ALLOW,
                resources=[f"arn:aws:kms:{Aws.REGION}:{Aws.ACCOUNT_ID}:key/*"],
            ),
        )

        cdk_synth_build_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "ssm:*",
                ],
                effect=iam.Effect.ALLOW,
                resources=[
                    f"arn:aws:ssm:{Aws.REGION}:{Aws.ACCOUNT_ID}:parameter/mlops/*",  # TODO: Add conditions
                ],
            ),
        )

        cdk_synth_build = codebuild.PipelineProject(
            self,
            "CDKSynthBuild",
            project_name=f"sagemaker-cdk-synth-build-{project_id}-{project_name}",
            role=cdk_synth_build_role, # type: ignore
            build_spec=codebuild.BuildSpec.from_source_filename("buildspec.yml"),
            environment=codebuild.BuildEnvironment(
                build_image=codebuild.LinuxArmBuildImage.AMAZON_LINUX_2_STANDARD_3_0,
                environment_variables={
                    "MODEL_PACKAGE_GROUP_NAME": codebuild.BuildEnvironmentVariable(
                        value=model_package_group_name
                    ),
                    "PROJECT_ID": codebuild.BuildEnvironmentVariable(value=project_id),
                    "PROJECT_NAME": codebuild.BuildEnvironmentVariable(
                        value=project_name
                    ),
                },
            ),
        )

        # Seedcode checkin

        codebuild_role = iam.Role.from_role_name(
            self,
            "SMProductsCodeBuildRole",
            role_name="MLOpsServiceCatalogProductsCodeBuildRole",
            mutable=False,
        )

        seedcode_checkin_project = codebuild.Project(
            self, 
            'GitSeedCodeCheckinProject',
            project_name=f"sagemaker-{project_name}-{project_id}-git-seedcodecheckin",
            source=codebuild.Source.s3(
                bucket=s3.Bucket.from_bucket_name(self, 'seedcodebucket', f"sagemaker-servicecatalog-seedcode-{Aws.REGION}"),
                path="bootstrap/GitRepositorySeedCodeCheckinCodeBuildProject-v1.1.zip",
            ),
            build_spec=codebuild.BuildSpec.from_source_filename('buildspec.yml'),
            environment=codebuild.BuildEnvironment(
                build_image=codebuild.LinuxBuildImage.STANDARD_7_0,
                compute_type=codebuild.ComputeType.SMALL
            ),
            role=codebuild_role,
            # role=iam.Role.from_role_arn(self, 'CodeBuildRole',f"arn:{Aws.PARTITION}:iam::{Aws.ACCOUNT_ID}:role/service-role/AmazonSageMakerServiceCatalogProductsCodeBuildRole"),
            timeout=aws_cdk.Duration.minutes(14)
        )

        seedcode_checkin_trigger_lambda = aws_lambda.Function(
            self,
            'GitSeedCodeCheckinProjectTriggerLambda',
            description='To trigger the codebuild project for the seedcode checkin',
            runtime=aws_lambda.Runtime.PYTHON_3_12,
            function_name=f"sagemaker-{project_id}-git-seedcodecheckin",
            timeout=aws_cdk.Duration.seconds(900),
            handler='index.lambda_handler',
            role=iam.Role.from_role_arn(self, 'LambdaRole', f"arn:{Aws.PARTITION}:iam::{Aws.ACCOUNT_ID}:role/MLOpsServiceCatalogProductsLambdaRole"),
            code=aws_lambda.Code.from_inline("""
import boto3
import cfnresponse
import os
import time


# This function should be triggered by the custom resource in the cfn template, Called along with the
# seedcode information (what code needs to be populated), the git repository information (where it
# needs to be populated) and the git codestar connection information. This would inturn trigger
# the codebuild which does the population of the seedcode
def lambda_handler(event, context):
    responseData = {}
    if event["RequestType"] == "Create":
        client = boto3.client("codebuild")
        response = client.start_build(
            projectName=os.environ["CodeBuildProjectName"],
            environmentVariablesOverride=get_build_environment_variables_override(
                event
            ),
            secondarySourcesOverride=get_secondary_sources_override(event),
        )
        poll_timeout = (
            840  # This Value is assigned based on the codebuild project timeout value
        )
        max_poll_time = time.time() + poll_timeout
        build_status = poll_and_get_build_status(
            client, response["build"]["id"], max_poll_time
        )
        if build_status != "SUCCEEDED":
            if time.time() > max_poll_time and build_status == "IN_PROGRESS":
                failure_reason = (
                    "Codebuild to checkin seedcode did not complete within "
                    + poll_timeout
                    + " seconds"
                )
            else:
                failure_reason = (
                    "Codebuild to checkin seedcode has status " + build_status
                )
                cfnresponse.send(
                    event,
                    context,
                    cfnresponse.FAILED,
                    responseData,
                    reason=failure_reason,
                )
        else:
            responseData["url"] = get_repository_url(event)
            cfnresponse.send(event, context, cfnresponse.SUCCESS, responseData)
    else:
        cfnresponse.send(event, context, cfnresponse.SUCCESS, responseData)


def get_build_environment_variables_override(event):
    return [
        {
            "name": "GIT_REPOSITORY_BRANCH",
            "value": event["ResourceProperties"]["GIT_REPOSITORY_BRANCH"],
            "type": "PLAINTEXT",
        },
        {
            "name": "GIT_REPOSITORY_URL",
            "value": get_repository_url(event),
            "type": "PLAINTEXT",
        },
    ]


def get_secondary_sources_override(event):
    return [
        {
            "location": "{}/{}".format(
                event["ResourceProperties"]["SEEDCODE_BUCKET_NAME"],
                event["ResourceProperties"]["SEEDCODE_BUCKET_KEY"],
            ),
            "type": "S3",
            "sourceIdentifier": "source",
        }
    ]


def get_repository_url(event):
    parsed_connection_arn = parse_arn(
        event["ResourceProperties"]["GIT_REPOSITORY_CONNECTION_ARN"]
    )
    url_prefix = "codeconnections"
    if "codestar-connections" in parsed_connection_arn["service"]:
        url_prefix = "codestar-connections"
    return "https://{}.{}.amazonaws.com/git-http/{}/{}/{}/{}.git".format(
        url_prefix,
        parsed_connection_arn["region"],
        parsed_connection_arn["account"],
        parsed_connection_arn["region"],
        parsed_connection_arn["resource"],
        event["ResourceProperties"]["GIT_REPOSITORY_FULL_NAME"],
    )


def parse_arn(arn):
    # http://docs.aws.amazon.com/general/latest/gr/aws-arns-and-namespaces.html
    elements = arn.split(":", 5)
    result = {
        "arn": elements[0],
        "partition": elements[1],
        "service": elements[2],
        "region": elements[3],
        "account": elements[4],
        "resource": elements[5],
        "resource_type": None,
    }
    if "/" in result["resource"]:
        result["resource_type"], result["resource"] = result["resource"].split("/", 1)
    elif ":" in result["resource"]:
        result["resource_type"], result["resource"] = result["resource"].split(":", 1)
    return result


def poll_and_get_build_status(client, build_id, max_poll_time):
    # usually it takes around 70 to 85 seconds for initializing the codebuild                    and
    # for the seedcode to get checked in
    initial_poll_interval = 60
    poll_interval = 15
    time.sleep(initial_poll_interval)
    build_status = "IN_PROGRESS"
    while build_status == "IN_PROGRESS" and time.time() < max_poll_time:
        build_status = client.batch_get_builds(ids=[build_id])["builds"][0][
            "buildStatus"
        ]
        time.sleep(poll_interval)
    return build_status"""),
            environment={
                'CodeBuildProjectName': seedcode_checkin_project.project_name
            }
        )

        sagemaker_seed_code_checkin_project_trigger_lambda_invoker = aws_cdk.CustomResource(
            self,
            'SageMakerSeedCodeCheckinProjectTriggerLambdaInvoker',
            resource_type="Custom::LambdaInvoker",
            service_token=seedcode_checkin_trigger_lambda.function_arn,
            properties={
                'SEEDCODE_BUCKET_NAME': deployment.deployed_bucket.bucket_name,
                'SEEDCODE_BUCKET_KEY': f"seedcode/{Fn.select(0, deployment.object_keys)}",
                'GIT_REPOSITORY_FULL_NAME': f"{owner}/{repository}",
                'GIT_REPOSITORY_BRANCH': 'main',
                'GIT_REPOSITORY_CONNECTION_ARN': connection_arn
            },
        )

        sagemaker_seed_code_checkin_project_trigger_lambda_invoker_wait_handle = aws_cdk.CfnWaitConditionHandle(self, 'SageMakerSeedCodeCheckinProjectTriggerLambdaInvokerWaitHandle')
        sagemaker_seed_code_checkin_project_trigger_lambda_invoker_wait_handle.node.add_dependency(sagemaker_seed_code_checkin_project_trigger_lambda_invoker)

        sagemaker_seed_code_checkin_project_trigger_lambda_invoker_wait_condition = aws_cdk.CfnWaitCondition(
            self, 
            'SageMakerSeedCodeCheckinProjectTriggerLambdaInvokerWaitCondition',
            timeout='10',
            count=0,
            handle=sagemaker_seed_code_checkin_project_trigger_lambda_invoker_wait_handle.ref
        )

        sagemaker_code_repository = sagemaker.CfnCodeRepository(
            self,
            'SageMakerCodeRepository',
            code_repository_name=f'sagemaker-{project_id}-repository',
            git_config=sagemaker.CfnCodeRepository.GitConfigProperty(
                branch='main',
                repository_url=sagemaker_seed_code_checkin_project_trigger_lambda_invoker.get_att('url').to_string()
            )
        )

        # end seedcode check in

        # code build to include security scan over cloudformation template
        security_scan = codebuild.Project(
            self,
            "SecurityScanTooling",
            build_spec=codebuild.BuildSpec.from_object(
                {
                    "version": 0.2,
                    "env": {
                        "shell": "bash",
                        "variables": {
                            "TemplateFolder": "./*.template.json",
                            "FAIL_BUILD": "true",
                        },
                    },
                    "phases": {
                        "install": {
                            "runtime-versions": {"ruby": 3.2},
                            "commands": [
                                "export date=`date +%Y-%m-%dT%H:%M:%S.%NZ`",
                                "echo Installing cfn_nag - `pwd`",
                                "gem install cfn-nag",
                                "echo cfn_nag installation complete `date`",
                            ],
                        },
                        "build": {
                            "commands": [
                                "echo Starting cfn scanning `date` in `pwd`",
                                "echo 'RulesToSuppress:\n- id: W58\n  reason: W58 is an warning raised due to Lambda functions require permission to write CloudWatch Logs, although the lambda role contains the policy that support these permissions cgn_nag continues to through this problem (https://github.com/stelligent/cfn_nag/issues/422)' > cfn_nag_ignore.yml",  # this is temporary solution to an issue with W58 rule with cfn_nag
                                'mkdir report || echo "dir report exists"',
                                "SCAN_RESULT=$(cfn_nag_scan --fail-on-warnings --deny-list-path cfn_nag_ignore.yml --input-path  ${TemplateFolder} -o json > ./report/cfn_nag.out.json && echo OK || echo FAILED)",
                                "echo Completed cfn scanning `date`",
                                "echo $SCAN_RESULT",
                                "echo $FAIL_BUILD",
                                """if [[ "$FAIL_BUILD" = "true" && "$SCAN_RESULT" = "FAILED" ]]; then printf "\n\nFailing pipeline as possible insecure configurations were detected\n\n" && exit 1; fi""",
                            ]
                        },
                    },
                    "artifacts": {"files": "./report/cfn_nag.out.json"},
                }
            ),
            environment=codebuild.BuildEnvironment(
                build_image=codebuild.LinuxBuildImage.STANDARD_7_0,
            ),
            project_name=f"sagemaker-security-scan-{project_id}-{project_name}"
        )

        source_artifact = codepipeline.Artifact(artifact_name="GitSource")
        cdk_synth_artifact = codepipeline.Artifact(artifact_name="CDKSynth")
        cfn_nag_artifact = codepipeline.Artifact(artifact_name="CfnNagScanReport")

        deploy_code_pipeline = codepipeline.Pipeline(
            self,
            "DeployPipeline",
            cross_account_keys=True,
            pipeline_name=pipeline_name,
            artifact_bucket=pipeline_artifact_bucket,
        )

        # add a source stage
        source_stage = deploy_code_pipeline.add_stage(stage_name="Source")
        source_stage.add_action(
            codepipeline_actions.CodeStarConnectionsSourceAction(
                connection_arn=connection_arn,
                action_name="Source",
                output=source_artifact,
                owner=owner,
                repo=repository,
                branch="main",
            )
        )

        # add a build stage
        build_stage = deploy_code_pipeline.add_stage(stage_name="Build")

        build_stage.add_action(
            codepipeline_actions.CodeBuildAction(
                action_name="Synth",
                input=source_artifact,
                outputs=[cdk_synth_artifact],
                project=cdk_synth_build, # type: ignore
            )
        )

        # add a security evaluation stage for cloudformation templates
        security_stage = deploy_code_pipeline.add_stage(stage_name="SecurityEvaluation")

        security_stage.add_action(
            codepipeline_actions.CodeBuildAction(
                action_name="CFNNag",
                input=cdk_synth_artifact,
                outputs=[cfn_nag_artifact],
                project=security_scan, # type: ignore
            )
        )


        deploy_code_pipeline.add_stage(
            stage_name="DeployPreProd",
            actions=[
                codepipeline_actions.CloudFormationCreateUpdateStackAction(
                    action_name="Deploy_CFN_PreProd",
                    run_order=1,
                    template_path=cdk_synth_artifact.at_path("preprod.template.json"),
                    stack_name=f"{project_name}-{construct_id}-preprod",
                    admin_permissions=False,
                    replace_on_failure=True,
                    role=iam.Role.from_role_arn(
                        self,
                        "PreProdActionRole",
                        f"arn:aws:iam::{preprod_account}:role/cdk-hnb659fds-deploy-role-{preprod_account}-{deployment_region}",
                        mutable=False,
                    ),
                    deployment_role=iam.Role.from_role_arn(
                        self,
                        "PreProdDeploymentRole",
                        f"arn:aws:iam::{preprod_account}:role/cdk-hnb659fds-cfn-exec-role-{preprod_account}-{deployment_region}",
                        mutable=False,
                    ),
                    cfn_capabilities=[
                        CfnCapabilities.AUTO_EXPAND,
                        CfnCapabilities.NAMED_IAM,
                    ],
                ),
                codepipeline_actions.ManualApprovalAction(
                    action_name="Approve_Prod",
                    run_order=2,
                    additional_information="Approving deployment for prod",
                ),
            ],
        )

        deploy_code_pipeline.add_stage(
            stage_name="DeployProd",
            actions=[
                codepipeline_actions.CloudFormationCreateUpdateStackAction(
                    action_name="Deploy_CFN_Prod",
                    run_order=1,
                    template_path=cdk_synth_artifact.at_path("prod.template.json"),
                    stack_name=f"{project_name}-{construct_id}-prod",
                    admin_permissions=False,
                    replace_on_failure=True,
                    role=iam.Role.from_role_arn(
                        self,
                        "ProdActionRole",
                        f"arn:aws:iam::{prod_account}:role/cdk-hnb659fds-deploy-role-{prod_account}-{deployment_region}",
                        mutable=False,
                    ),
                    deployment_role=iam.Role.from_role_arn(
                        self,
                        "ProdDeploymentRole",
                        f"arn:aws:iam::{prod_account}:role/cdk-hnb659fds-cfn-exec-role-{prod_account}-{deployment_region}",
                        mutable=False,
                    ),
                    cfn_capabilities=[
                        CfnCapabilities.AUTO_EXPAND,
                        CfnCapabilities.NAMED_IAM,
                    ],
                ),
            ],
        )

        if create_model_event_rule:
            # CloudWatch rule to trigger model pipeline when a status change event
            # happens to the model package group
            _ = events.Rule(
                self,
                "ModelEventRule",
                event_pattern=events.EventPattern(
                    source=["aws.sagemaker"],
                    detail_type=["SageMaker Model Package State Change"],
                    detail={
                        "ModelPackageGroupName": [model_package_group_name],
                        "ModelApprovalStatus": ["Approved", "Rejected"],
                    },
                ),
                targets=[targets.CodePipeline(deploy_code_pipeline)],
            )
        else:
            # CloudWatch rule to trigger the deploy CodePipeline when the build
            # CodePipeline has succeeded
            _ = events.Rule(
                self,
                "BuildCodePipelineEventRule",
                event_pattern=events.EventPattern(
                    source=["aws.codepipeline"],
                    detail_type=["CodePipeline Pipeline Execution State Change"],
                    detail={
                        "pipeline": [f"{project_name}-build"],
                        "state": ["SUCCEEDED"],
                    },
                ),
                targets=[targets.CodePipeline(deploy_code_pipeline)],
            )
