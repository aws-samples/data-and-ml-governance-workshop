import os

import aws_cdk as cdk
from aws_cdk import Stack, Tags
from aws_cdk import aws_iam as iam
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_servicecatalog as servicecatalog
from constructs import Construct
from service_catalog.ml_admin_products.sagemaker_studio_domain import (
    SagemakerStudioDomain,
)


class ServiceCatalogMLAdmin(Stack):
    def __init__(
        self, scope: Construct, construct_id: str, ml_workloads_org_path: str, **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Service Catalog Assets bucket
        sc_product_artifact_bucket = s3.Bucket(
            self,
            "SCProductArtifactBucket",
            removal_policy=cdk.RemovalPolicy.DESTROY,
            bucket_name=f"sc-ml-admin-artifact-bucket-{os.environ['CDK_DEFAULT_ACCOUNT']}-{os.environ['CDK_DEFAULT_REGION']}",
            enforce_ssl=True,
        )

        # Policy for access from workload OU
        central_bucket_policy = iam.PolicyStatement(
            actions=["s3:Get*"],
            resources=[sc_product_artifact_bucket.arn_for_objects("*")],
            principals=[iam.AnyPrincipal()],
            conditions={
                "ForAnyValue:StringLike": {
                    "aws:PrincipalOrgPaths": [ml_workloads_org_path]
                },
            },
        )
        sc_product_artifact_bucket.add_to_resource_policy(central_bucket_policy)

        # Service Catalog Portfolio
        portfolio = servicecatalog.Portfolio(
            self,
            "ML_Admins_Portfolio",
            display_name="ML Admins Portfolio",
            provider_name="ML Admin Team",
            description="Main products for ML Accounts",
        )

        # Adding product for ML Accounts
        sagemaker_studio_domain = servicecatalog.CloudFormationProduct(
            self,
            "Sagemaker Studio Domain",
            product_name="Sagemaker Studio Domain",
            owner="Global ML Team",
            product_versions=[
                servicecatalog.CloudFormationProductVersion(
                    cloud_formation_template=servicecatalog.CloudFormationTemplate.from_product_stack(
                        SagemakerStudioDomain(
                            self,
                            "SagemakerStudioTemplate",
                            asset_bucket=sc_product_artifact_bucket,
                        )
                    ),
                    product_version_name="v2",
                    validate_template=True,
                )
            ],
            description="Products for ML Admin",
            support_email="ml_admins@example.com",
        )

        portfolio.add_product(sagemaker_studio_domain)

        # General tags applied to all resources created on this scope
        # Tags.of(self).add("key", "value")  # TODO: specify tags
