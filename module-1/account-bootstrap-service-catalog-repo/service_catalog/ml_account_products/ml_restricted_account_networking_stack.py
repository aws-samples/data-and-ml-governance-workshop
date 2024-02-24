from aws_cdk import (
    aws_servicecatalog as servicecatalog,
    aws_ssm as ssm,
    CfnParameter,
    CfnOutput,
)
from constructs import Construct
from service_catalog.ml_account_products.constructs.restricted_infra import (
    RestrictedNetwork,
)


class MLRestrictedNetworkInfraStack(servicecatalog.ProductStack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # CloudFormation parameters

        vpc_secondary_cidr = CfnParameter(
            self,
            "VpcSecondaryCidr",
            type="String",
            description="Secondary cidr for VPC (check with Network Admin for value)",
            allowed_pattern="(\\d{1,3})\\.(\\d{1,3})\\.(\\d{1,3})\\.(\\d{1,3})/(\\d{1,2})",
        ).value_as_string

        transit_gateway_id = CfnParameter(
            self,
            "TransitGatewayId",
            type="String",
            description="Id of the TGW to attach to vpc",
        ).value_as_string

        # Network

        self.restricted_network = RestrictedNetwork(
            self, "RestrictedNetwork", transit_gateway_id, vpc_secondary_cidr
        )

        # SSM Parameters

        ssm.StringParameter(
            self,
            "VPCIDParameter",
            parameter_name="/vpc/id",
            string_value=self.restricted_network.vpc.vpc_id,
        )

        ssm.StringListParameter(
            self,
            "PrivateSubnetIDsParameter",
            parameter_name="/vpc/subnets/isolated/ids",
            string_list_value=[
                subnet.subnet_id
                for subnet in self.restricted_network.vpc.isolated_subnets
            ],
        )

        ssm.StringParameter(
            self,
            "DefaultSecurityGroupIDParameter",
            parameter_name="/vpc/sg/id",
            string_value=self.restricted_network.vpc.vpc_default_security_group,
        )

        # Cloudformation outputs
        CfnOutput(
            self,
            "VpcId",
            value=self.restricted_network.vpc.vpc_id,
            export_name="vpc-id",
        )

        isolated_subnets = [
            subnet.subnet_id for subnet in self.restricted_network.vpc.isolated_subnets
        ]

        CfnOutput(
            self,
            "PrivateSubnetIds",
            value=",".join(isolated_subnets),
            export_name="private-subnet-ids",
        )

        CfnOutput(
            self,
            "SecurityGroupId",
            value=self.restricted_network.vpc.vpc_default_security_group,
            export_name="default-security-group-id",
        )
