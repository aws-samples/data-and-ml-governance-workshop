# SageMaker Build - Train Pipelines

This folder contains all the SageMaker Pipelines of your project.

`buildspec.yml` defines how to run a pipeline after each commit to this repository.
`ml_pipelines/` contains the SageMaker pipelines definitions.
The expected output of the your main pipeline (here `training/pipeline.py`) is a model registered to SageMaker Model Registry.

`scripts/` contains the underlying scripts run by the steps of your SageMaker Pipelines. For example, if your SageMaker Pipeline runs a Processing Job as part of a Processing Step, the code being run inside the Processing Job should be defined in this folder.

# Run pipeline from command line from this folder

```
pip install -e .

run-pipeline --module-name ml_pipelines.training.pipeline --role-arn YOUR_SAGEMAKER_EXECUTION_ROLE_ARN --kwargs '{"region":"us-east-1"}'
```
