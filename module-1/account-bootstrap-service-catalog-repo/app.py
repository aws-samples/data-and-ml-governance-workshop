#!/usr/bin/env python3
import aws_cdk as cdk
from aws_cdk import Aspects
from cdk_nag import AwsSolutionsChecks
from cdk_pipelines.cdk_pipelines import CdkPipelineStack

app = cdk.App()
CdkPipelineStack(app, "AccountInfraServiceCatalogPipeline",
    description="CI/CD CDK Pipelines for Sagemaker Accounts Infrastructure",
     env={
         'region': app.node.try_get_context("region"),
         'account': app.node.try_get_context("pipeline_account")
     }
    )
Aspects.of(app).add(AwsSolutionsChecks())

app.synth()
