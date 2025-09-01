import boto3
import botocore
from fastapi import HTTPException

s3_client = boto3.client("s3")

def get_s3_client():
    return s3_client

def ensure_unique_s3_key(bucket_name: str, key: str):
    try:
        s3_client.head_object(Bucket=bucket_name, Key=key)
        raise HTTPException(status_code=409, detail="Conflict")
    except botocore.exceptions.ClientError:
        return