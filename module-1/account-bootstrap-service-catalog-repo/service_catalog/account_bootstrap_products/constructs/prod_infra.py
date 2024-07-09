from aws_cdk import (
    aws_ec2 as ec2,
)
from constructs import Construct


class ProdNetwork(Construct):
    """
    This construct creates the following resources:

    * VPC with 3 private subnets and 3 tgw subnets in 3 AZs
    * Transit Gateway attachment to the VPC for corp network connectivity
    * VPC Endpoints for Interface type services
    """

    def __init__(self, scope: Construct, construct_id: str, transit_gateway_id: str, vpc_secondary_cidr: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # VPC

        self.vpc = ec2.Vpc(
            self,
            "PrimaryVPC",
            ip_addresses=ec2.IpAddresses.cidr(self.node.try_get_context('VpcCidr')),
            max_azs=3,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="Private",
                    subnet_type=ec2.SubnetType.PRIVATE_ISOLATED,
                    cidr_mask=24,
                ),
            ],
            enable_dns_hostnames=True,
            enable_dns_support=True
        )

        ec2.CfnVPCCidrBlock(self, "SecondaryCIDR",
            vpc_id=self.vpc.vpc_id,
            cidr_block=vpc_secondary_cidr
            )

        # Transit Gateway attachment to the VPC
        self.tgw_attachment = ec2.CfnTransitGatewayAttachment(
            self,
            id="tgw-vpc-attachment",
            transit_gateway_id=transit_gateway_id,
            vpc_id=self.vpc.vpc_id,
            subnet_ids=[subnet.subnet_id for subnet in self.vpc.isolated_subnets],
        )

        # VPC Endpoints

        interface_endpoints = [
            ec2.InterfaceVpcEndpointAwsService.CLOUDWATCH,
            ec2.InterfaceVpcEndpointAwsService.CLOUDWATCH_LOGS,
            ec2.InterfaceVpcEndpointAwsService.CODECOMMIT,
            ec2.InterfaceVpcEndpointAwsService.CODECOMMIT_GIT,
            ec2.InterfaceVpcEndpointAwsService.ECR,
            ec2.InterfaceVpcEndpointAwsService.ECR_DOCKER,
            ec2.InterfaceVpcEndpointAwsService.KMS,
            ec2.InterfaceVpcEndpointAwsService.SAGEMAKER_API,
            ec2.InterfaceVpcEndpointAwsService.SAGEMAKER_RUNTIME,
            ec2.InterfaceVpcEndpointAwsService.SAGEMAKER_NOTEBOOK,
            ec2.InterfaceVpcEndpointAwsService.SERVICE_CATALOG,
            ec2.InterfaceVpcEndpointAwsService.SSM,
            ec2.InterfaceVpcEndpointAwsService.STS,
        ]

        for service in interface_endpoints:
            self.vpc.add_interface_endpoint(
                f"VpcEndpoint{service.short_name}",
                service=service
            )

        self.vpc.add_gateway_endpoint(
            "S3Endpoint", 
            service=ec2.GatewayVpcEndpointAwsService.S3
        )