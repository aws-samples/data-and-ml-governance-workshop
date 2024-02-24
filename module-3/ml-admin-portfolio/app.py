#!/usr/bin/env python3
import os

import aws_cdk as cdk

# For consistency with TypeScript code, `cdk` is the preferred import name for
# the CDK's core module.  The following line also imports it as `core` for use
# with examples from the CDK Developer's Guide, which are in the process of
# being updated to use `cdk`.  You may delete this import if you don't need it.

from cdk_pipelines.cdk_pipelines import CdkPipelineStack

app = cdk.App()
CdkPipelineStack(app, "MLAdminServiceCatalogPipeline",
    description="CI/CD CDK Pipelines for ML Admin Service Catalog",
    env=cdk.Environment(
        account=os.environ["CDK_DEFAULT_ACCOUNT"],
        region=os.environ["CDK_DEFAULT_REGION"])
    )

app.synth()
