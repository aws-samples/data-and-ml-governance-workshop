from aws_cdk import Stack, Stage
from aws_cdk import aws_codecommit as codecommit
from aws_cdk import pipelines as pipelines
from service_catalog.account_bootstrap_portfolio import (
    ServiceCatalogBootstrapAccounts,
)
from constructs import Construct


class AccountBootstrappingServiceCatalog(Stage):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        _ = ServiceCatalogBootstrapAccounts(self, "AccountBootstrappingPortfolio")


class CdkPipelineStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        hub_account = self.node.try_get_context("hub_account")
        hub_region = self.node.try_get_context("region")
        repo = codecommit.Repository(
            self,
            "Repo",
            repository_name="account-bootstrap-service-catalog-repo",
            description="CDK Code with ML Infra Service Catalog products",
        )

        pipeline = pipelines.CodePipeline(
            self,
            "Pipeline",
            pipeline_name="account-bootstrap-service-catalog-pipeline",
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
            AccountBootstrappingServiceCatalog(
                self,
                "BootstrapAccount",
                env={"account": hub_account, "region": hub_region},
            )
        )

        # General tags applied to all resources created on this scope (self)
        # Tags.of(self).add("key", "value")
