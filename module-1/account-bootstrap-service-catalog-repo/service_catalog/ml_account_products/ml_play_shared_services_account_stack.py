import aws_cdk as cdk
from aws_cdk import CfnOutput, CfnParameter
from aws_cdk import aws_ecr as ecr
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_sagemaker as sagemaker
from aws_cdk import aws_servicecatalog as servicecatalog
from aws_cdk import aws_ssm as ssm
from constructs import Construct
from service_catalog.ml_account_products.constructs.play_infra import PlayNetwork
from service_catalog.ml_account_products.constructs.sm_roles import SagemakerRoles


class MLPlaySharedServicesInfraStack(servicecatalog.ProductStack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        account = cdk.Aws.ACCOUNT_ID
        region = cdk.Aws.REGION

        # CloudFormation parameters
        domain_name = CfnParameter(
            self,
            "StudioDomainName",
            type="String",
            description="Name to assign to the SageMaker Studio domain",
            default="ML-Shared-Services-Domain",
        ).value_as_string

        s3_bucket_prefix = CfnParameter(
            self,
            "S3BucketName",
            type="String",
            description="S3 bucket where data are stored",
            default="sagemaker-s3-bucket",
        ).value_as_string

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

        # Central artifacts

        ecr.Repository(
            self,
            "CentralRepository",
            repository_name="central-ml-engineering-repository",
            image_scan_on_push=True,
        )

        s3.Bucket(
            self,
            "Bucket",
            bucket_name=f"{s3_bucket_prefix}-{account}-{region}",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            versioned=True,
        )

        # Roles for Sagemaker Profiles
        sm_roles = SagemakerRoles(self, "sm-roles", s3_bucket_prefix)

        private_subnets = [
            subnet.subnet_id for subnet in self.play_network.vpc.private_subnets
        ]

        # create sagemaker studio domain
        sagemaker.CfnDomain(
            self,
            "sagemaker-domain",
            auth_mode="SSO",
            app_network_access_type="VpcOnly",
            default_user_settings=sagemaker.CfnDomain.UserSettingsProperty(
                execution_role=sm_roles.sagemaker_studio_role.role_arn,
                security_groups=[self.play_network.vpc.vpc_default_security_group],
                sharing_settings=sagemaker.CfnDomain.SharingSettingsProperty(),  # disable notebook output sharing
            ),
            domain_name=domain_name,
            subnet_ids=private_subnets,
            vpc_id=self.play_network.vpc.vpc_id,
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
