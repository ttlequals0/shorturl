import boto3
import hmac
import os
import random
import re
import string
import botocore
from botocore.client import Config
from clean_url import clean_url

AWS_REGION = os.environ['AWS_REGION']

DEBUG = True

KEY_RE = re.compile(r'^[a-z0-9_-]{1,64}$')
RESERVED = set(["admin", "admin_shrink_url"])

# generate a random string of n characters, lowercase and numbers
def generate_random(n):
  return ''.join(random.SystemRandom().choice(string.ascii_lowercase + string.digits) for _ in range(n))

# checks whether an object already exists in the Amazon S3 bucket
# we do a head_object, if it throws a 404 error then the object does not exist
def exists_s3_key(s3_client, bucket, key):
  try:
    resp = s3_client.head_object(Bucket=bucket, Key=key)
    return True
  except botocore.exceptions.ClientError as e:
    # if ListBucket access is granted, then missing file returns 404
    if (e.response['Error']['Code'] == "404"): return False
    # if ListBucket access is not granted, then missing file returns 403 (which is the case here)
    if (e.response['Error']['Code'] == "403"): return False
    print(e.response)
    raise e     # otherwise re-raise the exception

# pick a random 7-char id that is not already in use
def unique_random_key(s3, bucket):
  while (True):
    short_id = generate_random(7)
    if not(exists_s3_key(s3, bucket, "u/" + short_id)):
      return short_id
    print("We got a short_key collision: u/" + short_id + ". Retrying.")

def put_redirect(s3, bucket, short_id, target):
  return s3.put_object(Bucket=bucket,
                       Key="u/" + short_id,
                       Body=b"",
                       WebsiteRedirectLocation=target,
                       ContentType="text/plain")

def handler(event, context):
  print({k: v for k, v in event.items() if k != "secret"})
  BUCKET_NAME = os.environ['S3_BUCKET']   # from env variable

  # shared secret, supplied by the admin page. fails closed if unset.
  admin_secret = os.environ.get('ADMIN_SECRET', '')
  supplied = event.get("secret") or ""
  if not admin_secret or not hmac.compare_digest(str(supplied), admin_secret):
    return { "error": "Unauthorized: wrong or missing admin secret." }

  s3 = boto3.client('s3', config=Config(signature_version='s3v4'))

  cdn_prefix = event.get("cdn_prefix")
  native_url = event.get("url_long")
  custom_key = (event.get("custom_key") or "").strip().lower()
  rename_from = (event.get("rename_from") or "").strip().lower()
  overwrite = bool(event.get("overwrite"))

  # rename mode: the target URL comes from the existing object, not the form
  if rename_from:
    if not custom_key:
      return { "error": "A new name is required to rename a link." }
    try:
      resp = s3.head_object(Bucket=BUCKET_NAME, Key="u/" + rename_from)
    except botocore.exceptions.ClientError:
      return { "error": "No such short link: " + rename_from }
    native_url = resp.get('WebsiteRedirectLocation')
    if not native_url:
      return { "error": "u/" + rename_from + " has no redirect target." }

  if not native_url:
    return { "error": "A long URL is required." }

  note = ""

  # rename reuses the target already stored, so only new links get cleaned
  clean_note = ""
  if not rename_from and not event.get("keep_tracking"):
    native_url, removed = clean_url(native_url)
    if removed:
      clean_note = "Removed %d tracking parameter%s: %s." % (
        len(removed), "" if len(removed) == 1 else "s", ", ".join(removed))

  if custom_key:
    if not KEY_RE.match(custom_key):
      return { "error": "Name must be 1-64 characters of a-z, 0-9, - or _." }
    if custom_key in RESERVED:
      return { "error": "'" + custom_key + "' is reserved and would be shadowed by the admin routes." }
    if custom_key == rename_from:
      return { "error": "'" + custom_key + "' is already the name of that link." }

    if exists_s3_key(s3, BUCKET_NAME, "u/" + custom_key) and not(overwrite):
      # a rename that falls back to a random name would delete the original and
      # hand back something nobody asked for, so refuse instead
      if rename_from:
        return { "error": "'" + custom_key + "' is already taken. Tick overwrite to replace it." }
      short_id = unique_random_key(s3, BUCKET_NAME)
      note = "'" + custom_key + "' was already taken, so " + short_id + " was used instead."
    else:
      short_id = custom_key
  else:
    short_id = unique_random_key(s3, BUCKET_NAME)

  print("We got a valid short_key: u/" + short_id)

  put_redirect(s3, BUCKET_NAME, short_id, native_url)

  if rename_from and short_id != rename_from:
    s3.delete_object(Bucket=BUCKET_NAME, Key="u/" + rename_from)
    if not note:
      note = "Renamed from " + rename_from + " - that old link no longer works."

  if clean_note:
    note = (note + " " + clean_note).strip()

  public_short_url = "https://" + cdn_prefix + "/" + short_id;

  result = { "url_short": public_short_url, "url_long": native_url }
  if note:
    result["note"] = note
  return result
