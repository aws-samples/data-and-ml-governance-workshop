from aws_cdk import CfnOutput
from aws_cdk import aws_servicecatalog as servicecatalog
from aws_cdk import aws_ssm as ssm
from constructs import Construct
from service_catalog.ml_account_products.constructs.play_infra import PlayNetwork


class MLPlayNetworkInfraStack(servicecatalog.ProductStack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.play_network = PlayNetwork(self, "PlayNetwork")

        # SSM Parameters

        ssm.StringParameter(
            self,
            "VPCIDParameter",
            parameter_name="/vpc/id",
            string_value=self.play_network.vpc.vpc_id,
        )

        ssm.StringListParameter(
            self,
            "PrivateSubnetIDsParameter",
            parameter_name="/vpc/subnets/private/ids",
            string_list_value=[
                subnet.subnet_id for subnet in self.play_network.vpc.private_subnets
            ],
        )

        ssm.StringParameter(
            self,
            "DefaultSecurityGroupIDParameter",
            parameter_name="/vpc/sg/id",
            string_value=self.play_network.vpc.vpc_default_security_group,
        )

        # Cloudformation outputs
        CfnOutput(
            self, "VpcId", value=self.play_network.vpc.vpc_id, export_name="vpc-id"
        )

        private_subnets_list = [
            subnet.subnet_id for subnet in self.play_network.vpc.private_subnets
        ]

        CfnOutput(
            self,
            "PrivateSubnetIds",
            value=",".join(private_subnets_list),
            export_name="private-subnet-ids",
        )

        CfnOutput(
            self,
            "SecurityGroupId",
            value=self.play_network.vpc.vpc_default_security_group,
            export_name="default-security-group-id",
        )
