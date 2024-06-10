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
import logging
import pathlib
import boto3 as boto3
import numpy as np
import pandas as pd
import sagemaker
import yaml
import awswrangler as wr

from sagemaker.feature_store.feature_group import FeatureGroup

# preprocess data from ML DEV account using central glue table  

boto3.set_stream_logger("boto3.resources", boto3.logging.INFO)
print("preprocess-s3.py START #")

logger = logging.getLogger(__name__)

# read from arguments
parser = argparse.ArgumentParser()
parser.add_argument("--default_bucket", type=str, dest="default_bucket")
args = parser.parse_args()
print("arguments", args)

s3_output_bucket = f"s3://{args.default_bucket}/query_results/"


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


boto3_session = boto3.Session(aws_access_key_id=credentials['AccessKeyId'], 
                           aws_secret_access_key=credentials['SecretAccessKey'], 
                           aws_session_token=credentials['SessionToken'], region_name="us-east-1")

query='SELECT * FROM "rl_bankdb"."bank"'

try:
    # Retrieving the data from Amazon Athena
    model_data = wr.athena.read_sql_query(
        query,
        database='rl_bankdb',
        boto3_session=boto3_session,
        ctas_approach=False,
        keep_files=False
    )

    print("Query completed, data retrieved successfully!")
except Exception as e:
    print(f"Something went wrong... the error is:{e}")
    raise Exception(e)



# Feature prep - select cols
model_data = model_data[['nr.employed', 'emp.var.rate', 'cons.conf.idx', 'euribor3m', 'cons.price.idx']]

# rename cols
model_data = model_data.rename(columns={'nr.employed': 'NumberEmployed', 'emp.var.rate': 'EmpVarRate', 'cons.conf.idx': 'ConsConfIdx', 'euribor3m': 'Euribor3m', 'cons.price.idx': 'ConsPriceIdx'})

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

print("prepare_data.py END")
