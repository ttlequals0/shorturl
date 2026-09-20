import os

import boto3
import botocore
from botocore.client import Config

S3_BUCKET = os.environ['S3_BUCKET']


def handler(event, context):
  key = "u/" + (event.get("Key") or "")
  s3 = boto3.client('s3', config=Config(signature_version='s3v4'))

  # the message is matched by the 404 integration response. letting the
  # exception escape instead hands the caller a traceback carrying the bucket
  # name and the function's file paths.
  try:
    resp = s3.head_object(Bucket=S3_BUCKET, Key=key)
  except botocore.exceptions.ClientError:
    raise Exception("NotFound")

  redirect_url = resp.get('WebsiteRedirectLocation')
  if not redirect_url:
    raise Exception("NotFound")

  return {"Redirect": redirect_url}
