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
from aws_cdk import Aws
from aws_cdk import aws_codebuild as codebuild
from aws_cdk import aws_codepipeline as codepipeline
from aws_cdk import aws_codepipeline_actions as codepipeline_actions
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_s3_deployment as s3deploy
from aws_cdk import aws_sagemaker as sagemaker
from aws_cdk import Fn
from constructs import Construct


class BuildPipelineConstruct(Construct):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        project_name: str,
        project_id: str,
        s3_artifact: s3.IBucket,
        pipeline_artifact_bucket: s3.IBucket,
        model_package_group_name: str,
        owner: str,
        repository: str,
        connection_arn: str,
        deployment: s3deploy.BucketDeployment ,
        build_env: dict | None = None,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Define resource names
        pipeline_name = f"sagemaker-{project_name}-{construct_id}"
        pipeline_description = f"{project_name} Model Build Pipeline"


        codebuild_role = iam.Role.from_role_name(
            self,
            "SMProductsCodeBuildRole",
            role_name="MLOpsServiceCatalogProductsCodeBuildRole",
            mutable=False,
        )

        codepipeline_role = iam.Role.from_role_name(
            self,
            "SMProductsCodePipelineRole",
            role_name="MLOpsServiceCatalogProductsCodePipelineRole",
            mutable=False,
        )

        event_role = iam.Role.from_role_name(
            self,
            "SMProductsEventsRole",
            role_name="MLOpsServiceCatalogProductsEventsRole",
            mutable=False,
        )

        sagemaker_execution_role = iam.Role.from_role_name(
            self,
            "SageMakerExecutionRole",
            role_name="MLOpsServiceCatalogProductsExecutionRole",
            mutable=False,
        )


        environment_variables = {
            "SAGEMAKER_PROJECT_NAME": codebuild.BuildEnvironmentVariable(
                value=project_name
            ),
            "SAGEMAKER_PROJECT_ID": codebuild.BuildEnvironmentVariable(
                value=project_id
            ),
            "MODEL_PACKAGE_GROUP_NAME": codebuild.BuildEnvironmentVariable(
                value=model_package_group_name
            ),
            "AWS_REGION": codebuild.BuildEnvironmentVariable(value=Aws.REGION),
            "SAGEMAKER_PIPELINE_NAME": codebuild.BuildEnvironmentVariable(
                value=pipeline_name,
            ),
            "SAGEMAKER_PIPELINE_DESCRIPTION": codebuild.BuildEnvironmentVariable(
                value=pipeline_description,
            ),
            "SAGEMAKER_PIPELINE_ROLE_ARN": codebuild.BuildEnvironmentVariable(  # TODO: replace with SageMakerSDK configuration file
                value=sagemaker_execution_role.role_arn,
            ),
            "ARTIFACT_BUCKET": codebuild.BuildEnvironmentVariable(  # TODO: replace with SageMakerSDK configuration file
                value=s3_artifact.bucket_name
            ),
            "ARTIFACT_BUCKET_KMS_ID": codebuild.BuildEnvironmentVariable(  # TODO: replace with SageMakerSDK configuration file
                value=s3_artifact.encryption_key.key_id
            ),
        }

        if build_env:
            project_build_env = {
                k: codebuild.BuildEnvironmentVariable(value=o) for k, o in build_env.items()
            }

            environment_variables = {**environment_variables, **project_build_env}

        assert (
            s3_artifact.encryption_key is not None
        )  # resolve ambiguity in encryption key type



        # Seedcode checkin
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
            # code=aws_lambda.Code.from_inline("import boto3\nimport cfnresponse\nimport os\nimport time\n\n#\
            #         This function should be triggered by the custom resource in the cfn template,\
            #         Called along with the\n# seedcode information (what code needs to be populated),\
            #         the git repository information (where it\n# needs to be populated) and\
            #         the git codestar connection information. This would inturn trigger\n#\
            #         the codebuild which does the population of the seedcode\ndef lambda_handler(event,\
            #         context):\n  responseData = {}\n  if event['RequestType'] == 'Create':\n\
            #            client = boto3.client('codebuild')\n    response = client.start_build(\n\
            #              projectName=os.environ['CodeBuildProjectName'],\n      environmentVariablesOverride=get_build_environment_variables_override(event),\n\
            #              secondarySourcesOverride=get_secondary_sources_override(event)\n\
            #            )\n    poll_timeout = 840 # This Value is assigned based on the codebuild\
            #         project timeout value\n    max_poll_time = time.time() + poll_timeout\n\
            #            build_status = poll_and_get_build_status(client, response['build']['id'],\
            #         max_poll_time)\n    if (build_status != 'SUCCEEDED'):\n      if (time.time()\
            #         > max_poll_time and build_status == 'IN_PROGRESS'):\n        failure_reason\
            #         = 'Codebuild to checkin seedcode did not complete within ' + poll_timeout\
            #         + ' seconds'\n      else:\n        failure_reason = 'Codebuild to checkin\
            #         seedcode has status ' + build_status\n      cfnresponse.send(event, context,\
            #         cfnresponse.FAILED, responseData, reason=failure_reason)\n    else:\n\
            #              responseData['url'] = get_repository_url(event)\n      cfnresponse.send(event,\
            #         context, cfnresponse.SUCCESS, responseData)\n  else:\n    cfnresponse.send(event,\
            #         context, cfnresponse.SUCCESS, responseData)\n\ndef get_build_environment_variables_override(event):\n\
            #          return [\n    {\n      'name': 'GIT_REPOSITORY_BRANCH',\n      'value':\
            #         event['ResourceProperties']['GIT_REPOSITORY_BRANCH'],\n      'type': 'PLAINTEXT'\n\
            #            },\n    {\n      'name': 'GIT_REPOSITORY_URL',\n      'value': get_repository_url(event),\n\
            #              'type': 'PLAINTEXT'\n    }\n  ]\n\ndef get_secondary_sources_override(event):\n\
            #          return [\n    {\n      'location': '{}/{}'.format(event['ResourceProperties']['SEEDCODE_BUCKET_NAME'],\
            #         event['ResourceProperties']['SEEDCODE_BUCKET_KEY']),\n      'type': 'S3',\n\
            #              'sourceIdentifier': 'source'\n    }\n  ]\n  \ndef get_repository_url(event):\n\
            #          parsed_connection_arn = parse_arn(event['ResourceProperties']['GIT_REPOSITORY_CONNECTION_ARN'])\n\
            #          url_prefix = 'codeconnections'\n  if 'codestar-connections' in parsed_connection_arn['service']:\n\
            #            url_prefix = 'codestar-connections'\n  return 'https://{}.{}.amazonaws.com/git-http/{}/{}/{}/{}.git'.format(url_prefix,\
            #         \n    parsed_connection_arn['region'], parsed_connection_arn['account'],\
            #         parsed_connection_arn['region'], parsed_connection_arn['resource'], \n\
            #            event['ResourceProperties']['GIT_REPOSITORY_FULL_NAME'])\n  \ndef parse_arn(arn):\n\
            #          # http://docs.aws.amazon.com/general/latest/gr/aws-arns-and-namespaces.html\n\
            #          elements = arn.split(':', 5)\n  result = {\n    'arn': elements[0],\n\
            #            'partition': elements[1],\n    'service': elements[2],\n    'region':\
            #         elements[3],\n    'account': elements[4],\n    'resource': elements[5],\n\
            #            'resource_type': None\n  }\n  if '/' in result['resource']:\n    result['resource_type'],\
            #         result['resource'] = result['resource'].split('/',1)\n  elif ':' in result['resource']:\n\
            #            result['resource_type'], result['resource'] = result['resource'].split(':',1)\n\
            #          return result\n\ndef poll_and_get_build_status(client, build_id, max_poll_time):\n\
            #          # usually it takes around 70 to 85 seconds for initializing the codebuild\
            #         and\n  # for the seedcode to get checked in\n  initial_poll_interval =\
            #         60\n  poll_interval = 15\n  time.sleep(initial_poll_interval)\n  build_status='IN_PROGRESS'\n\
            #          while build_status == 'IN_PROGRESS' and time.time() < max_poll_time:\n\
            #              build_status = client.batch_get_builds(ids=[build_id])['builds'][0]['buildStatus']\n\
            #              time.sleep(poll_interval)\n  return build_status\n"),
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

        #end seedcode checck in
        
        sm_pipeline_build = codebuild.PipelineProject(
            self,
            "SMPipelineBuild",
            project_name=f"sagemaker-{project_name}-{construct_id}",
            role=codebuild_role,  # TODO: figure out what actually this role would need
            build_spec=codebuild.BuildSpec.from_source_filename("buildspec.yml"),
            environment=codebuild.BuildEnvironment(
                build_image=codebuild.LinuxArmBuildImage.AMAZON_LINUX_2_STANDARD_3_0,
                environment_variables=environment_variables,
            ),
        )

       

        source_artifact = codepipeline.Artifact(artifact_name="GitSource")

        build_pipeline = codepipeline.Pipeline(
            self,
            "Pipeline",
            pipeline_name=pipeline_name,
            artifact_bucket=pipeline_artifact_bucket,
            role=codepipeline_role,
        )

        # add a source stage
        source_stage = build_pipeline.add_stage(stage_name="Source")
        source_stage.add_action(
            codepipeline_actions.CodeStarConnectionsSourceAction(
                connection_arn=connection_arn,
                action_name="Source",
                output=source_artifact,
                owner=owner,
                repo=repository,
                branch="main",
                role=codepipeline_role,
            )
        )

        # add a build stage
        build_stage = build_pipeline.add_stage(stage_name="Build")
        build_stage.add_action(
            codepipeline_actions.CodeBuildAction(
                action_name="SMPipeline",
                input=source_artifact,
                project=sm_pipeline_build, # type: ignore
                role=codepipeline_role,
            )
        )