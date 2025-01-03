import os
from importlib import import_module
from pathlib import Path

import aws_cdk as cdk
from aws_cdk import Stack, Tags
from aws_cdk import aws_iam as iam
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_servicecatalog as servicecatalog
from aws_cdk import aws_codeconnections as codeconnections
from constructs import Construct

central_account_id = os.getenv("CDK_DEFAULT_ACCOUNT", cdk.Aws.ACCOUNT_ID)


class ServiceCatalogSmProjects(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        codeconnection: codeconnections.CfnConnection,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        ml_workloads_org_path = self.node.try_get_context("MLWorkloadsOrgPath")

        sc_product_artifact_bucket = s3.Bucket(
            self,
            "SCProductArtifactBucket",
            removal_policy=cdk.RemovalPolicy.DESTROY,
            bucket_name=f"sc-artifact-bucket-{os.environ['CDK_DEFAULT_ACCOUNT']}-{os.environ['CDK_DEFAULT_REGION']}",
            enforce_ssl=True,
            auto_delete_objects=True,
        )

        # Policy for access from workload OU
        central_bucket_policy = iam.PolicyStatement(
            actions=["s3:Get*"],
            resources=[sc_product_artifact_bucket.arn_for_objects("*")],
            principals=[iam.AnyPrincipal()], # type: ignore
            conditions={
                "ForAnyValue:StringLike": {
                    "aws:PrincipalOrgPaths": [ml_workloads_org_path]
                },
            },
        )
        sc_product_artifact_bucket.add_to_resource_policy(central_bucket_policy)

        # TODO: check if restrictive policy work
        # iam.PolicyStatement(
        #     actions=["s3:GetObject*", "s3:GetBucket*", "s3:List*"],
        #     effect=iam.Effect.ALLOW,
        #     resources=[
        #         sc_product_artifact_bucket.bucket_arn,
        #         sc_product_artifact_bucket.arn_for_objects("*"),
        #     ],
        #     principals=[iam.AnyPrincipal()],
        #     conditions={
        #         "ForAnyValue:StringEquals": {
        #             "aws:CalledVia": ["cloudformation.amazonaws.com"]
        #         },
        #         "Bool": {"aws:ViaAWSService": True},
        #         "ForAnyValue:StringLike": {
        #             "aws:PrincipalOrgPaths": [ml_workloads_org_path]
        #         },
        #     },
        # )

        launch_role = iam.Role.from_role_name(
            self, "LaunchRole", "MLOpsServiceCatalogProductsLaunchRole", mutable=False
        )

        # Service Catalog Portfolio
        portfolio_build = servicecatalog.Portfolio(
            self,
            "MLOpsBuildPortfolio",
            display_name="SM Projects Portfolio for model build",
            provider_name="ML Admin Team",
            description="Products for SM Projects",
        )

        # Service Catalog Portfolio
        portfolio_deploy = servicecatalog.Portfolio(
            self,
            "MLOpsDeployPortfolio",
            display_name="SM Projects Portfolio for model deployment",
            provider_name="ML Admin Team",
            description="Products for SM Projects",
        )

        servicecatalog.CfnPortfolioPrincipalAssociation(
            self,
            "BuildPortfolioRoleAccessGrant",
            portfolio_id=portfolio_build.portfolio_id,
            principal_arn="arn:aws:iam:::role/*sagemaker*",
            principal_type="IAM_PATTERN",
        )
        servicecatalog.CfnPortfolioPrincipalAssociation(
            self,
            "DeployPortfolioRoleAccessGrant",
            portfolio_id=portfolio_deploy.portfolio_id,
            principal_arn="arn:aws:iam:::role/*sagemaker*",
            principal_type="IAM_PATTERN",
        )

        # Adding sagemaker projects products
        self.add_all_products(
            portfolio=portfolio_build,
            launch_role=launch_role,
            sc_product_artifact_bucket=sc_product_artifact_bucket,
            codeconnection=codeconnection,
            templates_directory="service_catalog/sm_projects_products/building",
        )

        self.add_all_products(
            portfolio=portfolio_deploy,
            launch_role=launch_role,
            sc_product_artifact_bucket=sc_product_artifact_bucket,
            codeconnection=codeconnection,
            templates_directory="service_catalog/sm_projects_products/deploy",
        )

    def add_all_products(
        self,
        portfolio: servicecatalog.Portfolio,
        launch_role: iam.IRole,
        codeconnection: codeconnections.CfnConnection,
        templates_directory: str = "service_catalog/sm_projects_products",
        **kwargs,
    ):
        templates_path = Path(templates_directory)
        [
            SmProject(
                self,
                file.stem.replace("_product_stack", ""),
                portfolio=portfolio,
                template_py_file=file,
                launch_role=launch_role,
                codeconnection=codeconnection,
                **kwargs,
            )
            for file in templates_path.glob("**/*_product_stack.py")
        ]


class SmProject(cdk.NestedStack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        portfolio: servicecatalog.Portfolio,
        template_py_file: Path,
        launch_role: iam.IRole,
        sc_product_artifact_bucket: s3.Bucket,
        codeconnection: codeconnections.CfnConnection,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        module_name: str = template_py_file.stem
        short_name = module_name.replace("_product_stack", "")
        module_path: str = (
            (template_py_file.parent / module_name).as_posix().replace(os.path.sep, ".")
        )
        template_module = import_module(module_path)
        try:
            description = template_module.MLOpsStack.get_description()
        except Exception:
            description = "Products for SageMaker Projects"

        try:
            template_name = template_module.MLOpsStack.get_template_name()
        except Exception:
            template_name = short_name
        try:
            support_email = template_module.MLOpsStack.get_support_email()
        except Exception:
            support_email = "ml_admins@example.com"

        sm_projects_product = servicecatalog.CloudFormationProduct(
            self,
            short_name,
            product_name=template_name,
            owner="Global ML Team",
            product_versions=[
                servicecatalog.CloudFormationProductVersion(
                    cloud_formation_template=servicecatalog.CloudFormationTemplate.from_product_stack(
                        template_module.MLOpsStack(
                            self,
                            "project",
                            asset_bucket=sc_product_artifact_bucket,
                            **kwargs,
                        )
                    ),
                    product_version_name="v1",
                    validate_template=True,
                )
            ],
            description=description,
            support_email=support_email,
        )
        portfolio.add_product(sm_projects_product)
        portfolio.set_local_launch_role(
            sm_projects_product,
            launch_role=launch_role,  # type: ignore
            description="Launch using MLOpsServiceCatalogProductsLaunchRole",
        )

        Tags.of(sm_projects_product).add(
            key="sagemaker:studio-visibility", value="true"
        )
