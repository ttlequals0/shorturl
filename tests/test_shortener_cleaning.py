#!/usr/bin/env python3
"""Tests the cleaning wiring inside the shortener handler.

boto3 is not installed locally and S3 is not reachable, so both are stubbed in
sys.modules before shortener is imported. Run: python3 tests/test_shortener_cleaning.py
"""

import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src", "shortener"))

SECRET = "test-secret"
FAILURES = []


class ClientError(Exception):
  def __init__(self, response):
    self.response = response


class FakeS3(object):
  def __init__(self):
    self.store = {}

  def head_object(self, Bucket, Key):
    if Key in self.store:
      return {"WebsiteRedirectLocation": self.store[Key]}
    raise ClientError({"Error": {"Code": "404"}})

  def put_object(self, Bucket, Key, Body, WebsiteRedirectLocation, ContentType):
    self.store[Key] = WebsiteRedirectLocation

  def delete_object(self, Bucket, Key):
    del self.store[Key]


CURRENT = FakeS3()

botocore = types.ModuleType("botocore")
botocore.exceptions = types.ModuleType("botocore.exceptions")
botocore.exceptions.ClientError = ClientError
botocore.client = types.ModuleType("botocore.client")
botocore.client.Config = lambda **kwargs: None
boto3 = types.ModuleType("boto3")
boto3.client = lambda name, config=None: CURRENT

sys.modules["boto3"] = boto3
sys.modules["botocore"] = botocore
sys.modules["botocore.exceptions"] = botocore.exceptions
sys.modules["botocore.client"] = botocore.client

os.environ["AWS_REGION"] = "us-east-1"
os.environ["S3_BUCKET"] = "test-bucket"
os.environ["ADMIN_SECRET"] = SECRET

import index as shortener


def call(**payload):
  """Run the handler against a fresh fake bucket. Returns (result, store)."""
  global CURRENT
  CURRENT = FakeS3()
  seed = payload.pop("_seed", {})
  CURRENT.store.update(seed)
  payload.setdefault("secret", SECRET)
  payload.setdefault("cdn_prefix", "short.example.com")
  return shortener.handler(payload, None), CURRENT.store


def check(name, got, want):
  if got != want:
    FAILURES.append("%s\n  got:  %r\n  want: %r" % (name, got, want))


DIRTY = "https://example.com/p?id=42&utm_source=news&fbclid=abc"
CLEAN = "https://example.com/p?id=42"

result, store = call(url_long=DIRTY, custom_key="demo")
check("stores the cleaned url as the redirect target", store["u/demo"], CLEAN)
check("returns the cleaned url to the caller", result["url_long"], CLEAN)
check("reports what it removed",
      result.get("note"), "Removed 2 tracking parameters: utm_source, fbclid.")

result, store = call(url_long=DIRTY, custom_key="demo", keep_tracking=True)
check("keep_tracking leaves the stored url alone", store["u/demo"], DIRTY)
check("keep_tracking adds no note", result.get("note"), None)

result, store = call(url_long=CLEAN, custom_key="demo")
check("a url with nothing to strip gets no note", result.get("note"), None)

result, _ = call(url_long="https://example.com/p?utm_source=news", custom_key="demo")
check("uses the singular for a single parameter",
      result.get("note"), "Removed 1 tracking parameter: utm_source.")

result, store = call(rename_from="old", custom_key="new", _seed={"u/old": DIRTY})
check("rename does not rewrite the stored target", store["u/new"], DIRTY)
check("rename reports only the rename",
      result.get("note"), "Renamed from old - that old link no longer works.")

result, store = call(url_long=DIRTY, custom_key="taken", _seed={"u/taken": "https://other.example"})
check("a name collision keeps the original target",
      store["u/taken"], "https://other.example")
check("the cleaning note is appended to the collision note, not replacing it",
      result.get("note", "").endswith("Removed 2 tracking parameters: utm_source, fbclid."),
      True)
check("the collision note still explains the fallback",
      result.get("note", "").startswith("'taken' was already taken"), True)

result, _ = call(url_long=DIRTY, custom_key="demo", secret="wrong")
check("an unauthorized call still fails before any cleaning",
      result, {"error": "Unauthorized: wrong or missing admin secret."})

if FAILURES:
  print("FAIL: %d of the checks did not pass\n" % len(FAILURES))
  print("\n\n".join(FAILURES))
  sys.exit(1)

print("ok - all checks passed")
