# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# SPDX-License-Identifier: MIT-0
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of this
# software and associated documentation files (the "Software"), to deal in the Software
# without restriction, including without limitation the rights to use, copy, modify,
# merge, publish, distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A
# PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
# HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
# SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

# import argparse
import argparse
import os
import time
import boto3 as boto3
import numpy as np
import pandas as pd
import sagemaker
import yaml

# preprocess data from CFS account via Central Governanc(CG) account
# centralfeaturestore glue db exists in CG account and accessed via LF remote link


boto3.set_stream_logger("boto3.resources", boto3.logging.INFO)
print("preprocess-cfs.py START #")

def read_parameters():
    """
    Reads job parameters configured.
    Returns:
        (Namespace): read parameters
    """
    with open("/opt/ml/processing/input/code/scripts/job-config.yml", "r") as f:
        params = yaml.safe_load(f)

    return params

# Reading job parameters
job_params = read_parameters()

# read from arguments
parser = argparse.ArgumentParser()
parser.add_argument("--default_bucket", type=str, dest="default_bucket")
arguments = parser.parse_args()
print("arguments", arguments)

s3_output_bucket = f"s3://{arguments.default_bucket}/query_results/"

model_data = []

sts_client = boto3.client('sts')
accountId = sts_client.get_caller_identity()["Account"]


# Call the assume_role method of the STSConnection object and pass the role
# ARN and a role session name.
assumed_role_object=sts_client.assume_role(
    RoleArn="arn:aws:iam::" +accountId + ":role/AthenaConsumerAssumeRole",
    RoleSessionName="AssumeRoleSession1"
)

# From the response that contains the assumed role, get the temporary 
# credentials that can be used to make subsequent API calls
credentials=assumed_role_object['Credentials']

# Use the temporary credentials that AssumeRole returns to make a 
# connection to Amazon S3  
athena_resource=boto3.client(
    'athena',
    aws_access_key_id=credentials['AccessKeyId'],
    aws_secret_access_key=credentials['SecretAccessKey'],
    aws_session_token=credentials['SessionToken'],
)

# Use the Amazon S3 resource object that is now configured with the 
# credentials to access your S3 buckets. 

feature_group_arn = job_params["feature_group_arn"]
output_location = 's3://sagemaker-' +accountId +'-mlops'

response = athena_resource.start_query_execution(
            QueryString='SELECT * FROM "rl_fs_centralfeaturestore"."' + feature_group_arn + '" limit 10;',
            QueryExecutionContext={'Database': 'rl_fs_centralfeaturestore'},
            ResultConfiguration={"OutputLocation": output_location}
        )

qid = response.get('QueryExecutionId')
athenaResults = athena_wait_for_job_completion(qid, athena_resource) # type: ignore
model_data = results_to_df(athenaResults) # type: ignore

# One hot encode categorical variables
model_data = pd.get_dummies(model_data)

# print(model_data.head(5))
# encode True/False to 1/0
bool_cols = model_data.select_dtypes(include=["bool"]).columns
for col in bool_cols:
    model_data[col] = model_data[col].astype(int)

# move the predicted colum to first - as XGB expects
# Add predicting column at the beginning of the dataframe
model_data["y_yes"] = pd.NA
y_yes = [1, 0]
model_data["y_yes"] = model_data["y_yes"].apply(
    lambda x: np.random.choice(y_yes, p=[0.64, 0.36])
)
predict_col = model_data.pop("y_yes")
model_data.insert(0, "y_yes", predict_col)


# split the data into train, validate, test:
train_data, val_data, test_data = np.split(
    model_data.sample(frac=1, random_state=1729),
    [int(0.7 * len(model_data)), int(0.9 * len(model_data))],
)

base_dest = "/opt/ml/processing/"
train_path = base_dest + "train"
val_path = base_dest + "validation"
test_path = base_dest + "test"


try:
    os.makedirs(train_path)
    os.makedirs(val_path)
    os.makedirs(test_path)
except Exception:
    pass

train_data.to_csv(train_path + "/train.csv", index=False, header=None)
val_data.to_csv(val_path + "/validation.csv", index=False, header=None)
test_data.to_csv(test_path + "/test.csv", index=False, header=None)

print("preprocess-cfs.py END")

#utility functions

def athena_wait_for_job_completion(queryId, athena_client):

    state = "RUNNING"
    response_query_result=''

    while True:
        time.sleep(1)
        query_details = athena_client.get_query_execution(
            QueryExecutionId=queryId
        )
        state = query_details['QueryExecution']['Status']['State']
        if state == 'SUCCEEDED':
            response_query_result = athena_client.get_query_results(
                QueryExecutionId=queryId
            )
            break
    
    return response_query_result

def results_to_df(results):
    columns = [
        col['Label']
        for col in results['ResultSet']['ResultSetMetadata']['ColumnInfo']
    ]
    listed_results = []
    for res in results['ResultSet']['Rows'][1:]:
     values = []
     for field in res['Data']:
        try:
            values.append(list(field.values())[0])
        except:
            values.append(list(' '))
        listed_results.append(
            dict(zip(columns, values))
            )
    df = pd.DataFrame(listed_results)
    dfo = copy_every_3rd_row(df)
    
    return dfo


