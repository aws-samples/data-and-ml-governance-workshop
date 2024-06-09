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

from aws_cdk import Aws
from aws_cdk import aws_codebuild as codebuild
from aws_cdk import aws_codecommit as codecommit
from aws_cdk import aws_codepipeline as codepipeline
from aws_cdk import aws_codepipeline_actions as codepipeline_actions
from aws_cdk import aws_iam as iam
from aws_cdk import aws_s3 as s3
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
        repository: codecommit.Repository,
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
            codepipeline_actions.CodeCommitSourceAction(
                action_name="Source",
                output=source_artifact,
                repository=repository,
                branch="main",
                event_role=event_role,
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