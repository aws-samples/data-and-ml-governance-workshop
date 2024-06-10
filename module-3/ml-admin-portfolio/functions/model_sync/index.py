import json
import os
from typing import Any, Dict, List
from xmlrpc.client import Boolean

import boto3
from aws_lambda_powertools import Logger
from aws_lambda_powertools.utilities.typing import LambdaContext
from botocore.exceptions import ClientError

logger = Logger()
sagemaker_client = boto3.client("sagemaker")
s3_client = boto3.client("s3")
paginator = sagemaker_client.get_paginator("list_model_packages")

destination_bucket_name = os.environ.get("ArtifactBucketName")


def copy_artifact(
    source_object_arn: str, destination_bucket_name: str, destination_prefix: str
):
    """
    Copy an object from one S3 bucket to another.

    Args:
        source_object_arn (str):
            The ARN of the source S3 object.
        destination_bucket_name (str):
            The name of the destination bucket.
        destination_prefix (str):
            The prefix path within the destination bucket.

    Returns:
        str:
            The ARN of the copied object in the destination bucket.
    """
    source_bucket_name, source_object_key = source_object_arn.removeprefix(
        "s3://"
    ).split("/", 1)
    s3_client.copy_object(
        Bucket=destination_bucket_name,
        Key=f"{destination_prefix}/{source_object_key}",
        CopySource={"Bucket": source_bucket_name, "Key": source_object_key},
    )
    return f"s3://{destination_bucket_name}/{destination_prefix}/{source_object_key}"


exclusion_list = ["ImageDigest"]


def upload_and_replace(
    data: Dict | List | str | Any, destination_bucket_name: str, destination_prefix: str
):
    """Recursively scan a structure to upload data to an S3 bucket, replacing S3 URLs.

    Args:
        data (Dict|List|str|Any): The data to upload. Can be a dict, list,
            string or other object.
        destination_bucket_name (str): The name of the destination S3 bucket.
        destination_prefix (str): The prefix path within the bucket.

    Returns:
        The uploaded data with any S3 URLs replaced by the new destination.
    """

    if isinstance(data, dict):
        return {
            k: upload_and_replace(v, destination_bucket_name, destination_prefix)
            for k, v in data.items()
            if k not in exclusion_list
        }
    elif isinstance(data, list):
        return [
            upload_and_replace(i, destination_bucket_name, destination_prefix)
            for i in data
        ]
    elif isinstance(data, str):
        return (
            copy_artifact(data, destination_bucket_name, destination_prefix)
            if data.startswith("s3://")
            else data
        )
    return data


def check_pkg_already_exists(
    source_model_package_arn: str, target_model_package_group: str
) -> Boolean:
    """Check if a model package already exists in a target model package group.

    Args:
        source_model_package_arn (str): The ARN of the source model package.
        target_model_package_group (str): The name of the target model package group.

    Returns:
        Boolean: True if a package with the same OriginalARN metadata property
            already exists in the target group, False otherwise.
    """

    for summary in paginator.paginate(ModelPackageGroupName=target_model_package_group):
        for package in summary["ModelPackageSummaryList"]:
            if (
                sagemaker_client.describe_model_package(
                    ModelPackageName=package["ModelPackageArn"]
                )["CustomerMetadataProperties"]["OriginalARN"]
                == source_model_package_arn
            ):
                return True
    return False


@logger.inject_lambda_context(log_event=True)
def lambda_handler(event, context: LambdaContext):
    source_model_package_arn = event["detail"]["ModelPackageArn"]
    logger.info(f"Source Model Package ARN: {source_model_package_arn}")

    model_package = sagemaker_client.describe_model_package(
        ModelPackageName=source_model_package_arn
    )
    source_account_id = source_model_package_arn.split(":")[4]
    model_package = sagemaker_client.describe_model_package(
        ModelPackageName=source_model_package_arn
    )

    mpg_name = model_package["ModelPackageGroupName"]
    # mpg_arn = f"{source_model_package_arn.split(':model-package/')[0]}:model-package-group/{model_package['ModelPackageGroupName']}"
    destination_prefix = f"{mpg_name}-{source_account_id}"
    target_model_package_group = f"{mpg_name}-{source_account_id}"

    try:
        # Check if the model package group already exists, and if the model package has already been synced
        sagemaker_client.describe_model_package_group(
            ModelPackageGroupName=target_model_package_group
        )

        if check_pkg_already_exists(
            source_model_package_arn, target_model_package_group
        ):
            logger.info(
                f"Model package {source_model_package_arn} already exists in {target_model_package_group}"
            )

            return {
                "statusCode": 200,
                "body": json.dumps(
                    f"Model package {source_model_package_arn} already exists in {target_model_package_group}"
                ),
            }

    except ClientError:
        logger.info(f"Creating model group {target_model_package_group}")
        sagemaker_client.create_model_package_group(
            ModelPackageGroupName=target_model_package_group
        )

    # scan the source model package for artifacts to upload to S3
    new_model_package = upload_and_replace(
        model_package, destination_bucket_name, destination_prefix  # type: ignore
    )
    assert isinstance(new_model_package, Dict)  # fix type linting errors

    try:
        create_model_package_input = dict(
            ModelPackageGroupName=target_model_package_group,
            InferenceSpecification=new_model_package["InferenceSpecification"],
            ModelApprovalStatus="PendingManualApproval",
            ModelPackageDescription=new_model_package.get(
                "ModelPackageDescription", ""
            ),
            CustomerMetadataProperties={"OriginalARN": source_model_package_arn},
        )

        if model_metrics := new_model_package.get("ModelMetrics", None):
            create_model_package_input = {
                **create_model_package_input,
                "ModelMetrics": model_metrics,
            }

        response = sagemaker_client.create_model_package(**create_model_package_input) # type: ignore
        package_arn = response["ModelPackageArn"]

    except ClientError as e:
        logger.error("Model Package creation failed.")
        return {"statusCode": 500, "body": json.dumps(e)}

    return {
        "statusCode": 200,
        "body": json.dumps(f"Copied artifacts and registered Model: {package_arn}"),
    }
