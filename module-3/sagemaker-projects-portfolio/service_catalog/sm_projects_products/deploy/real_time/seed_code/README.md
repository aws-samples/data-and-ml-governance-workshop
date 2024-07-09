# Overview

This repository is constructed as a cdk application. The `buildspec.yaml` in this folder will run:

```terminal
cdk synth
```

to generate CloudFormation templates that the CI/CD Pipeline (CodePipeline) will
use to deploy infrastructure in the respective aws accounts.

This repository in particular creates a SageMaker endpoint (for realtime inference) running inside a VPC.

## Explanation on VPC and Network pre-requirements

This repository however does not create the VPC. Instead it will create placeholders (CfnParameter),
reading values from Systems Manager Parameter Store (SSM) at CloudFormation deployment time in
the respective accounts (dev/preprod/prod) to create the endpoints inside a VPC.

It requires those values to be stored in the following SSM parameters in all accounts where an endpoint is deployed:

- `"/vpc/subnets/private/ids"`
- `"/vpc/sg/id"`

Those values are automatically created if you used the `mlops_infra` repository to
prepare your dev, preprod and prod accounts.

Additional configurations read at `cdk synth` time are stored in `config/`.
