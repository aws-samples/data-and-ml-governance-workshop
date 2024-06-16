#!/usr/bin/env python3
import os

import aws_cdk as cdk
from aws_cdk import Aspects
from cdk_nag import AwsSolutionsChecks
from cdk_pipelines.cdk_pipelines import CdkPipelineStack

app = cdk.App()
pipeline_stack = CdkPipelineStack(
    app,
    "SmProjectsServiceCatalogPipeline",
    description="CI/CD CDK Pipelines for Sagemaker Projects Service Catalog",
    env=cdk.Environment(
        account=os.environ["CDK_DEFAULT_ACCOUNT"],
        region=os.environ["CDK_DEFAULT_REGION"],
    ),
)
Aspects.of(app).add(AwsSolutionsChecks())

app.synth()
