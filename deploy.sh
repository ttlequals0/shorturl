#!/usr/bin/env bash
#
# Deploys the stack and pushes the admin page.
#
#   ./deploy.sh
#
# Environment:
#   STACK_NAME     stack and function name prefix   (default: shorturl)
#   AWS_REGION     region to deploy into            (default: us-east-1, or your CLI default)
#   STAGE_NAME     API Gateway stage                (default: prod)
#   ADMIN_SECRET   shared secret for the admin page (default: reuse existing, or generate)
#   ARTIFACTS_BUCKET  bucket for the packaged code  (default: derived from stack and account)

set -euo pipefail

STACK_NAME="${STACK_NAME:-shorturl}"
STAGE_NAME="${STAGE_NAME:-prod}"
AWS_REGION="${AWS_REGION:-$(aws configure get region || echo us-east-1)}"
export AWS_REGION

cd "$(dirname "$0")"

need() { command -v "$1" >/dev/null || { echo "missing: $1" >&2; exit 1; }; }
need aws
need zip

ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
ARTIFACTS_BUCKET="${ARTIFACTS_BUCKET:-${STACK_NAME}-artifacts-${ACCOUNT}-${AWS_REGION}}"

stack_exists() {
  aws cloudformation describe-stacks --stack-name "$STACK_NAME" >/dev/null 2>&1
}

output() {
  aws cloudformation describe-stacks --stack-name "$STACK_NAME" \
    --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" --output text
}

# ---- admin secret -----------------------------------------------------------
# an unset secret must not silently rotate the live one, so reuse what the
# deployed function already has and only generate on a first deploy.
if [ -z "${ADMIN_SECRET:-}" ]; then
  if stack_exists; then
    ADMIN_SECRET=$(aws lambda get-function-configuration \
      --function-name "$(aws cloudformation describe-stack-resource \
        --stack-name "$STACK_NAME" --logical-resource-id ShortenerFunction \
        --query 'StackResourceDetail.PhysicalResourceId' --output text)" \
      --query 'Environment.Variables.ADMIN_SECRET' --output text)
    echo "reusing the existing admin secret"
  else
    ADMIN_SECRET=$(openssl rand -base64 32)
    GENERATED=1
  fi
fi

# ---- artifacts bucket -------------------------------------------------------
if ! aws s3api head-bucket --bucket "$ARTIFACTS_BUCKET" 2>/dev/null; then
  echo "creating artifacts bucket $ARTIFACTS_BUCKET"
  if [ "$AWS_REGION" = "us-east-1" ]; then
    aws s3api create-bucket --bucket "$ARTIFACTS_BUCKET" >/dev/null
  else
    aws s3api create-bucket --bucket "$ARTIFACTS_BUCKET" \
      --create-bucket-configuration "LocationConstraint=$AWS_REGION" >/dev/null
  fi
fi

# ---- package and deploy -----------------------------------------------------
mkdir -p .build
echo "packaging"
aws cloudformation package \
  --template-file template.yaml \
  --s3-bucket "$ARTIFACTS_BUCKET" \
  --output-template-file .build/packaged.yaml >/dev/null

echo "deploying stack $STACK_NAME to $AWS_REGION"
aws cloudformation deploy \
  --template-file .build/packaged.yaml \
  --stack-name "$STACK_NAME" \
  --capabilities CAPABILITY_IAM \
  --no-fail-on-empty-changeset \
  --parameter-overrides "AdminSecret=$ADMIN_SECRET" "StageName=$STAGE_NAME"

# ---- admin page -------------------------------------------------------------
# the page lives in the mock integration's response template, so it is pushed
# separately and can be changed without a stack update
API_ID=$(output ApiId)
RESOURCE_ID=$(aws apigateway get-resources --rest-api-id "$API_ID" \
  --query "items[?path=='/admin'].id" --output text)

echo "pushing src/web/admin.html"
python3 - "$API_ID" "$RESOURCE_ID" <<'PY'
import json, subprocess, sys
api_id, resource_id = sys.argv[1], sys.argv[2]
html = open("src/web/admin.html", encoding="utf-8").read()
payload = {
    "restApiId": api_id,
    "resourceId": resource_id,
    "httpMethod": "GET",
    "statusCode": "200",
    "patchOperations": [{
        "op": "replace",
        "path": "/responseTemplates/application~1json",
        "value": html,
    }],
}
with open(".build/admin-patch.json", "w") as fh:
    json.dump(payload, fh)
subprocess.run(["aws", "apigateway", "update-integration-response",
                "--cli-input-json", "file://.build/admin-patch.json"],
               check=True, stdout=subprocess.DEVNULL)
PY

aws apigateway create-deployment --rest-api-id "$API_ID" \
  --stage-name "$STAGE_NAME" --description "admin page" >/dev/null

# ---- done -------------------------------------------------------------------
echo
echo "admin      $(output AdminUrl)"
echo "short link $(output BaseUrl)/<key>"
echo "bucket     $(output BucketName)"
if [ "${GENERATED:-}" = "1" ]; then
  echo
  echo "admin secret (shown once, store it now):"
  echo "  $ADMIN_SECRET"
fi
