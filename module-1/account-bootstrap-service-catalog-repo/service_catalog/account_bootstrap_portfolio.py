from aws_cdk import Stack
from aws_cdk import aws_servicecatalog as servicecatalog
from service_catalog.ml_account_products.ml_play_account_networking_stack import (
    MLPlayNetworkInfraStack,
)
from service_catalog.ml_account_products.ml_play_shared_services_account_stack import (
    MLPlaySharedServicesInfraStack,
)
from service_catalog.ml_account_products.ml_restricted_account_networking_stack import (
    MLRestrictedNetworkInfraStack,
)
from service_catalog.ml_account_products.ml_restricted_shared_services_account_stack import (
    MLRestrictedSharedServicesInfraStack,
)
from constructs import Construct


class ServiceCatalogBootstrapAccounts(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Service Catalog Portfolio
        portfolio = servicecatalog.Portfolio(
            self,
            "Bootstrap_Accounts_Portfolio",
            display_name="Bootstrap Accounts Portfolio",
            provider_name="Global Infra Team",
            description="Infrastructure to bootstrap Accounts",
        )

        # Adding product for ML Play Accounts
        ml_play_account_networking = servicecatalog.CloudFormationProduct(
            self,
            "ML_Play_Account",
            product_name="ML Play Account",
            owner="Global Infra Team",
            product_versions=[
                servicecatalog.CloudFormationProductVersion(
                    cloud_formation_template=servicecatalog.CloudFormationTemplate.from_product_stack(
                        MLPlayNetworkInfraStack(self, "ML_Account_Networking_Template")
                    ),
                    product_version_name="v2",
                    validate_template=True,
                )
            ],
            description="ML Play Account Networking provisioning Product",
            support_email="infra_support@example.com",
        )

        portfolio.add_product(ml_play_account_networking)

        # Adding product for ML Restricted Accounts
        ml_restricted_account_networking = servicecatalog.CloudFormationProduct(
            self,
            "ML_Restricted_Account",
            product_name="ML Restricted Account",
            owner="Global Infra Team",
            product_versions=[
                servicecatalog.CloudFormationProductVersion(
                    cloud_formation_template=servicecatalog.CloudFormationTemplate.from_product_stack(
                        MLRestrictedNetworkInfraStack(
                            self, "ML_Restricted_Account_Networking_Template"
                        )
                    ),
                    product_version_name="v1",
                    validate_template=True,
                )
            ],
            description="ML Restricted Account Networking provisioning Product",
            support_email="infra_support@example.com",
        )

        portfolio.add_product(ml_restricted_account_networking)

        # Adding product for ML Restricted Shared Service Infra Stack

        ml_restricted_shared_services = servicecatalog.CloudFormationProduct(
            self,
            "ML_Restricted_Shared_Services_Infra",
            product_name="ML Restricted Shared Services Account",
            owner="ML Infra Team",
            product_versions=[
                servicecatalog.CloudFormationProductVersion(
                    cloud_formation_template=servicecatalog.CloudFormationTemplate.from_product_stack(
                        MLRestrictedSharedServicesInfraStack(
                            self, "ML_Restricted_Shared_Services_Bootstrap_Template"
                        )
                    ),
                    product_version_name="v2",
                    validate_template=True,
                )
            ],
            description="ML Restricted Shared Services Bootstrapping Infra Provisioning Product",
            support_email="infra_support@example.com",
        )

        portfolio.add_product(ml_restricted_shared_services)

        # Adding product for ML Restricted Shared Service Infra Stack
        ml_play_shared_services = servicecatalog.CloudFormationProduct(
            self,
            "ML_Play_Shared_Services_Infra",
            product_name="ML Play Shared Services Account",
            owner="ML Infra Team",
            product_versions=[
                servicecatalog.CloudFormationProductVersion(
                    cloud_formation_template=servicecatalog.CloudFormationTemplate.from_product_stack(
                        MLPlaySharedServicesInfraStack(
                            self, "ML_Play_Shared_Services_Bootstrap_Template"
                        )
                    ),
                    product_version_name="v1",
                    validate_template=True,
                )
            ],
            description="ML Play Shared Services Bootstrapping Infra Provisioning Product",
            support_email="infra_support@example.com",
        )

        portfolio.add_product(ml_play_shared_services)

        # General tags applied to all resources created on this scope
        # Tags.of(self).add("key", "value")
