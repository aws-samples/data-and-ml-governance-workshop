from aws_cdk import Stack, Stage
from aws_cdk import aws_codecommit as codecommit
from aws_cdk import pipelines as pipelines
from common_infra.common_infra_stack import CommonInfraStack
from constructs import Construct
from service_catalog.ml_admin_portfolio import ServiceCatalogMLAdmin


class MLAdminServiceCatalog(Stage):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        ml_workloads_org_path = self.node.try_get_context("MLWorkloadsOrgPath")

        _ = ServiceCatalogMLAdmin(
            self,
            "MLAdminServiceCatalogPortfolio",
            ml_workloads_org_path=ml_workloads_org_path,
        )


class MLCommonInfra(Stage):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        ml_workloads_ou_id = self.node.try_get_context("MLWorkloadsOUId")
        ml_deployment_org_id = self.node.try_get_context("MLDeploymentOUId")
        ml_deployment_org_path = self.node.try_get_context("MLDeploymentOrgPath")

        _ = CommonInfraStack(
            self,
            "CommonInfra",
            ml_org_id=ml_workloads_ou_id,
            ml_deployment_org_id=ml_deployment_org_id,
            ml_deployment_org_path=ml_deployment_org_path,
        )


class CdkPipelineStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        hub_account = self.node.try_get_context("hub_account")
        hub_region = self.node.try_get_context("region")
        repo = codecommit.Repository(
            self,
            "Repo",
            repository_name="ml-admin-service-catalog-repo",
            description="CDK Code with ML Admins Service Catalog products",
        )

        pipeline = pipelines.CodePipeline(
            self,
            "Pipeline",
            pipeline_name="ml-admin-service-catalog-pipeline",
            synth=pipelines.ShellStep(
                "Synth",
                input=pipelines.CodePipelineSource.code_commit(repo, "main"),
                commands=[
                    "npm install -g aws-cdk && pip install -r requirements.txt",
                    "cdk synth",
                ],
            ),
        )

        wave = pipeline.add_wave("HubAccount")
        wave.add_stage(
            MLCommonInfra(
                self, "CommonInfra", env={"account": hub_account, "region": hub_region}
            )
        )
        wave.add_stage(
            MLAdminServiceCatalog(
                self,
                "MLAdminServiceCatalog",
                env={"account": hub_account, "region": hub_region},
            )
        )
        