#!/usr/bin/env python3
import os

import aws_cdk as cdk
from cdk_pipelines.cdk_pipelines import CdkPipelineStack

app = cdk.App()
CdkPipelineStack(app, "SmProjectsServiceCatalogPipeline",
    description="CI/CD CDK Pipelines for Sagemaker Projects Service Catalog",
    env=cdk.Environment(
        account=os.environ["CDK_DEFAULT_ACCOUNT"],
        region=os.environ["CDK_DEFAULT_REGION"])
    )

app.synth()
