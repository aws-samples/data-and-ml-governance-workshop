import json
import os

import boto3
import botocore
from aws_lambda_powertools import Logger
from aws_lambda_powertools.utilities.data_classes import EventBridgeEvent, event_source
from aws_lambda_powertools.utilities.typing import LambdaContext

logger = Logger()

tooling_account = os.getenv("CENTRAL_ACCOUNT_ID")
assert isinstance(tooling_account, str)
sagemaker_client = boto3.client("sagemaker")
region = os.getenv("AWS_REGION", "us-east-1")


@logger.inject_lambda_context
@event_source(data_class=EventBridgeEvent)
def handler(event: EventBridgeEvent, context: LambdaContext):
    details = event.detail

    model_package_group_arn = details["responseElements"]["modelPackageGroupArn"]
    assert isinstance(model_package_group_arn, str)
    model_package_group_name = model_package_group_arn.rsplit("/", 1)[0]
    account_id = context.invoked_function_arn.split(":")[4]

    resource_policy = write_cross_account_policy(
        model_package_group_name, account_id, region, tooling_account
    )

    try:
        sagemaker_client.put_model_package_group_policy(
            ModelPackageGroupName=model_package_group_name,
            ResourcePolicy=resource_policy,
        )
    except botocore.exceptions.ClientError as error:  # type: ignore
        logger.exception(error)
        raise error

    return {
        "statusCode": 200,
        "body": json.dumps(
            {
                "message": f"Added cross account policy to Model Package Group {model_package_group_name}",
            }
        ),
    }


def write_cross_account_policy(
    model_package_group_name: str, account_id: str, region: str, tooling_account: str
) -> str:
    """Generates an IAM policy document that allows cross-account access to a SageMaker model package group.

    Args:
        model_package_group_name (str): The name of the model package group.
        account_id (str): The AWS account ID of the account that owns the model package group.
        region (str): The AWS region of the model package group.
        tooling_account (str): The AWS account ID that needs access to the model package group.

    Returns:
        policy (str): The IAM policy document as a JSON-serialized dictionary.
    """

    policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "ModelPackageGroup",
                "Effect": "Allow",
                "Principal": {"AWS": f"arn:aws:iam::{tooling_account}:root"},
                "Action": "sagemaker:DescribeModelPackageGroup",
                "Resource": f"arn:aws:sagemaker:{region}:{account_id}:model-package-group/{model_package_group_name}",
            },
            {
                "Sid": "ModelPackages",
                "Effect": "Allow",
                "Principal": {"AWS": f"arn:aws:iam::{account_id}:root"},
                "Action": [
                    "sagemaker:DescribeModelPackage",
                    "sagemaker:ListModelPackages",
                    "sagemaker:UpdateModelPackage",
                    "sagemaker:CreateModel",
                ],
                "Resource": f"arn:aws:sagemaker:{region}:{account_id}:model-package/{model_package_group_name}/*",
            },
        ],
    }

    return json.dumps(policy)
