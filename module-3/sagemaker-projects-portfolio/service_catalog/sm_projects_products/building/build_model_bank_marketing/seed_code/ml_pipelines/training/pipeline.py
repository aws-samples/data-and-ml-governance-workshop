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

"""Bank Marketing SM Pipeline for process data from S3, train and register model.

                                               . -RegisterModel
                                              .
    Process-> Train -> Register .
                                              .
                                               . -(stop)

Implements a get_pipeline(**kwargs) method.
"""
import logging
import os
import boto3
import sagemaker
import sagemaker.session
from sagemaker import Model
from sagemaker.inputs import TrainingInput
from sagemaker.processing import FrameworkProcessor, ProcessingInput, ProcessingOutput
from sagemaker.sklearn import SKLearn
from sagemaker.workflow.model_step import ModelStep
from sagemaker.workflow.parameters import (
    ParameterInteger,
    ParameterString,
)
from sagemaker.workflow.pipeline import Pipeline
from sagemaker.workflow.pipeline_context import PipelineSession
from sagemaker.workflow.steps import CacheConfig, ProcessingStep, TrainingStep

# BASE_DIR = os.path.dirname(os.path.realpath(__file__))


boto3.set_stream_logger("boto3.resources", boto3.logging.INFO)
print("pipeline.py START #")

logger = logging.getLogger(__name__)


def get_session(region, default_bucket):
    """Gets the sagemaker session based on the region.

    Args:
        region: the aws region to start the session
        default_bucket: the bucket to use for storing the artifacts

    Returns:
        `sagemaker.session.Session instance
    """

    boto_session = boto3.Session(region_name=region)

    sagemaker_client = boto_session.client("sagemaker")
    runtime_client = boto_session.client("sagemaker-runtime")
    session = sagemaker.session.Session(
        boto_session=boto_session,
        sagemaker_client=sagemaker_client,
        sagemaker_runtime_client=runtime_client,
        default_bucket=default_bucket,
    )

    return session


def get_pipeline(
    region,
    role=None,
    default_bucket=None,
    model_package_group_name="BankMarketing",
    pipeline_name="model-build-bank-marketing",
    base_job_prefix="bank-marketing",
    bucket_kms_id=None,
):
    """Gets a SageMaker ML Pipeline instance working with on abalone data.

    Args:
        region: AWS region to create and run the pipeline.
        role: IAM role to create and run steps and pipeline.
        default_bucket: the bucket to use for storing the artifacts

    Returns:
        an instance of a pipeline
    """
    pipeline_session = PipelineSession()

    sagemaker_session = get_session(region, default_bucket)
    if role is None:
        role = sagemaker.session.get_execution_role(sagemaker_session)

    # parameters for pipeline execution
    input_src = ProcessingInput(
        source="scripts", destination="/opt/ml/processing/input/code/scripts/"
    )
    output_train = ProcessingOutput(
        output_name="train", source="/opt/ml/processing/train"
    )
    output_validation = ProcessingOutput(
        output_name="validation", source="/opt/ml/processing/validation"
    )
    output_test = ProcessingOutput(output_name="test", source="/opt/ml/processing/test")

    processing_instance_count = ParameterInteger(
        name="ProcessingInstanceCount", default_value=1
    )
    processing_instance_type = ParameterString(
        name="ProcessingInstanceType",
        default_value="ml.t3.xlarge",  # for ml.m5.large service quota need to lifted, in provision account
    )
    training_instance_count = ParameterInteger(
        name="TrainingInstanceCount", default_value=1
    )
    training_instance_type = ParameterString(
        name="TrainingInstanceType", default_value="ml.m4.xlarge"
    )
    model_approval_status = ParameterString(
        name="ModelApprovalStatus", default_value="PendingManualApproval"
    )
    # pipeline_cache = ParameterBoolean(name="EnablePipelineCache", default_value=False)
    cache_config = CacheConfig(enable_caching=False, expire_after="T24H")

    # Data processing step
    sklearn_processor = FrameworkProcessor(
        estimator_cls=SKLearn,
        framework_version="1.2-1",
        role=role,
        instance_type=processing_instance_type,
        instance_count=processing_instance_count,
        sagemaker_session=pipeline_session,
    )

    sts_client = boto3.client('sts')
    accountId = sts_client.get_caller_identity()["Account"]
    default_bucket = f"sagemaker-{accountId}-mlops"

    s3_object_key = os.environ.get('S3ObjectKey')

    input_data = f"s3://sagemaker-{accountId}-mlops/{s3_object_key}"

    prepare_step = ProcessingStep(
        name="PreprocessData",
        step_args=sklearn_processor.run(
            inputs=[input_src],
            outputs=[output_train, output_validation, output_test],
            code="preprocess.py",
            source_dir="scripts",
            arguments=["--default_bucket", default_bucket, "--input_data", input_data],
        ),
        cache_config=cache_config,
    )
    

    # The XGBoot training step:
    xgboost_container = sagemaker.image_uris.retrieve("xgboost", region, "latest")
    model_path = f"s3://{default_bucket}/{base_job_prefix}-train"
    xgb = sagemaker.estimator.Estimator(
        xgboost_container,
        role,
        instance_count=training_instance_count,
        instance_type=training_instance_type,
        output_path=model_path,
        sagemaker_session=pipeline_session,
    )
    xgb.set_hyperparameters(
        max_depth=5,
        eta=0.2,
        gamma=4,
        min_child_weight=6,
        subsample=0.8,
        silent=0,
        objective="binary:logistic",
        num_round=100,
    )
    trainer = xgb.fit(
        inputs={
            "train": TrainingInput(
                s3_data=prepare_step.properties.ProcessingOutputConfig.Outputs[
                    "train"
                ].S3Output.S3Uri,
                content_type="text/csv",
            ),
            "validation": TrainingInput(
                s3_data=prepare_step.properties.ProcessingOutputConfig.Outputs[
                    "validation"
                ].S3Output.S3Uri,
                content_type="text/csv",
            ),
        }
    )

    train_step = TrainingStep(
        name="Train", step_args=trainer, cache_config=cache_config
    )

    # Model register into pending:
    model = Model(
        image_uri=xgboost_container,
        model_data=train_step.properties.ModelArtifacts.S3ModelArtifacts,
        sagemaker_session=pipeline_session,
        role=role,
    )
    register_model = model.register(
        content_types=["text/csv"],
        response_types=["text/csv"],
        inference_instances=[training_instance_type],
        transform_instances=[training_instance_type],
        model_package_group_name=model_package_group_name,
        approval_status=model_approval_status,
    )
    register_model_step = ModelStep(name="RegisterModel", step_args=register_model)

    # pipeline instance
    pipeline = Pipeline(
        name=f"{base_job_prefix}-{pipeline_name}",
        parameters=[
            processing_instance_type,
            processing_instance_count,
            training_instance_type,
            training_instance_count,
            model_approval_status,
        ],
        steps=[prepare_step, train_step, register_model_step],
        sagemaker_session=sagemaker_session,
    )
    return pipeline
