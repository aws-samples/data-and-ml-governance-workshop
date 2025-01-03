import aws_cdk
from aws_cdk import Stack, Stage
from aws_cdk import pipelines as pipelines
from aws_cdk import aws_codeconnections as codeconnections
from constructs import Construct
from service_catalog.sm_projects_portfolio import ServiceCatalogSmProjects


class SmProjectsServiceCatalog(Stage):
    def __init__(self, scope: Construct, construct_id: str, codeconnection: codeconnections.CfnConnection, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        _ = ServiceCatalogSmProjects(self, "SmProjectsServiceCatalogPortfolio", codeconnection=codeconnection)


class CdkPipelineStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        hub_account = self.node.try_get_context("hub_account")
        hub_region = self.node.try_get_context("region")
        repo_owner = self.node.try_get_context('RepoOwner')

        connection = codeconnections.CfnConnection(self, 'Connection', connection_name='codeconnection-service-catalog', provider_type='GitHub')

        pipeline = pipelines.CodePipeline(
            self,
            "Pipeline",
            pipeline_name="sm-projects-service-catalog-pipeline",
            synth=pipelines.ShellStep(
                "Synth",
                input=pipelines.CodePipelineSource.connection(f"{repo_owner}/sm-projects-service-catalog-repo", "main", connection_arn=connection.attr_connection_arn),
                commands=[
                    "npm install -g aws-cdk && pip install -r requirements.txt",
                    "cdk synth",
                ],
            ),
        )

        wave = pipeline.add_wave("HubAccount")
        wave.add_stage(
            SmProjectsServiceCatalog(
                self,
                "SmProjectsServiceCatalogPortfolio",
                codeconnection=connection,
                env={"account": hub_account, "region": hub_region},
            )
        )
