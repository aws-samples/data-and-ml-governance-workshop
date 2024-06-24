from aws_cdk import Stack
from aws_cdk import aws_servicecatalog as servicecatalog

import os
import importlib

from constructs import Construct


class ServiceCatalogBootstrapAccounts(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Service Catalog Portfolio
        portfolio = servicecatalog.Portfolio(
            self,
            "Portfolio",
            display_name="Bootstrap Accounts Portfolio",
            provider_name="Global Infra Team",
            description="Infrastructure to bootstrap Accounts",
        )

        base_directory = os.path.join(os.path.dirname(__file__), "account_bootstrap_products", "products")
        product_stacks = find_product_stacks(base_directory)
        
        for file_path, module_name, product_name, version in product_stacks:
            ProductStack = import_product_stack(file_path, module_name)
            product_id = product_name.replace('-', '_')
            stack_name = f"{product_id}_Stack"
            print(product_name, product_id, stack_name)
            product = servicecatalog.CloudFormationProduct(self, product_id,
                product_name=product_name,
                owner="Global Infra Team",
                product_versions=[
                    servicecatalog.CloudFormationProductVersion(
                        cloud_formation_template=servicecatalog.CloudFormationTemplate.from_product_stack(
                            ProductStack(self, stack_name)
                        ),
                        product_version_name=version
                    )
                ]
            )
            
            portfolio.add_product(product)

def find_product_stacks(base_directory):
    product_stacks = []
    for root, _, files in os.walk(base_directory):
        for file in files:
            if file.endswith('_stack.py'):
                file_path = os.path.join(root, file)
                relative_path = os.path.relpath(file_path, base_directory)
                parts = relative_path.split(os.sep)
                if len(parts) >= 4:
                    # Construct module name for dynamic import
                    module_name = 'service_catalog.account_bootstrap_products.' + relative_path.replace('/', '.').replace('.py', '')
                    # Construct product name from the three levels before the file
                    product_name = '-'.join(parts[-4:-1])
                    # Extract version from the second last part of the path
                    version = parts[-2]
                    product_stacks.append((file_path, module_name, product_name, version))
    return product_stacks

def import_product_stack(file_path, module_name):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, 'ProductStack')