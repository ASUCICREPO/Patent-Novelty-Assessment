# Deployment Guide

- [Deployment Guide](#deployment-guide)
  - [Requirements](#requirements)
  - [Pre-Deployment](#pre-deployment)
    - [1. AWS Account Setup](#1-aws-account-setup)
    - [2. Install Required Tools](#2-install-required-tools)
    - [3. Configure AWS CLI](#3-configure-aws-cli)
    - [4. Enable Bedrock Model Access](#4-enable-bedrock-model-access)
    - [5. Create PatentView API Gateway](#5-create-patentview-api-gateway)
    - [6. Create Semantic Scholar API Gateway](#6-create-semantic-scholar-api-gateway)
  - [Deployment](#deployment)
    - [Method 1: Automated Deployment Script (Recommended)](#method-1-automated-deployment-script-recommended)
    - [Method 2: Manual CDK Deployment](#method-2-manual-cdk-deployment)
  - [Post-Deployment Configuration](#post-deployment-configuration)
    - [1. Create Agent Core Runtime](#1-create-agent-core-runtime)
    - [2. Configure Environment Variables](#2-configure-environment-variables)
    - [3. Update Agent Runtime ARN](#3-update-agent-runtime-arn)
    - [4. Redeploy Stack](#4-redeploy-stack)
  - [Verification](#verification)
  - [Troubleshooting](#troubleshooting)

## Requirements

Before you deploy, you must have the following:

- **AWS Account** with administrative access - [Sign up here](https://aws.amazon.com/free/)
- **AWS CLI** (version 2.x or later) - [Installation guide](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)
- **Node.js** (version 18.x or later) - [Download here](https://nodejs.org/)
- **npm** (comes with Node.js)
- **Docker** (for building container images) - [Install Docker](https://docs.docker.com/get-docker/)
- **Git** (for cloning the repository) - [Install Git](https://git-scm.com/downloads)
- **jq** (for JSON parsing in deployment script) - Install via `brew install jq` (macOS) or `apt-get install jq` (Linux)

## Pre-Deployment

### 1. AWS Account Setup

Ensure you have an AWS account with permissions to create:
- S3 buckets
- Lambda functions
- DynamoDB tables
- IAM roles and policies
- Bedrock resources (BDA projects, Agent Core runtimes)
- ECR repositories

### 2. Install Required Tools

Verify all required tools are installed:

```bash
# Check AWS CLI version
aws --version
# Expected: aws-cli/2.x.x or later

# Check Node.js version
node --version
# Expected: v18.x.x or later

# Check npm version
npm --version
# Expected: 9.x.x or later

# Check Docker version
docker --version
# Expected: Docker version 20.x.x or later

# Check jq version
jq --version
# Expected: jq-1.x or later
```

### 3. Configure AWS CLI

Configure AWS CLI with your credentials:

```bash
aws configure
```

When prompted, enter:
- **AWS Access Key ID**: Your access key
- **AWS Secret Access Key**: Your secret key
- **Default region name**: `us-west-2` (recommended) or your preferred region
- **Default output format**: `json`

**Important**: Note down your AWS region as you'll need it throughout deployment.

### 4. Enable Bedrock Model Access

Enable access to Claude 3.7 Sonnet in Amazon Bedrock:

1. Go to AWS Console → Amazon Bedrock → Model access
2. Click "Manage model access"
3. Enable "Claude 3.7 Sonnet" (model ID: `us.anthropic.claude-3-7-sonnet-20250219-v1:0`)
4. Click "Save changes"
5. Wait for status to change to "Access granted" (may take a few minutes)

### 5. Create PatentView API Gateway

Set up MCP Gateway for PatentView API access:

1. Go to AWS Console → Amazon Bedrock → Model Context Protocol (MCP)
2. Click "Create Gateway"
3. Configure gateway:
   - **Gateway Name**: `patentview-gateway`
   - **API Type**: REST API
   - **OpenAPI Specification**: Upload `docs/patentview_openapi_spec.json` from this repository
   - **Authentication**: OAuth 2.0 Client Credentials
4. Click "Create Gateway"
5. **Note down the following values** (you'll need them later):
   - Gateway URL (e.g., `https://xxxxxxxxxx.execute-api.us-west-2.amazonaws.com/prod/`)
   - Client ID
   - Client Secret
   - Token URL

### 6. Create Semantic Scholar API Gateway

Set up MCP Gateway for Semantic Scholar API access:

1. Go to AWS Console → Amazon Bedrock → Model Context Protocol (MCP)
2. Click "Create Gateway"
3. Configure gateway:
   - **Gateway Name**: `semantic-scholar-gateway`
   - **API Type**: REST API
   - **OpenAPI Specification**: Upload `docs/semantic_scholar_openapi_spec.json` from this repository
   - **Authentication**: OAuth 2.0 Client Credentials
4. Click "Create Gateway"
5. **Note down the following values** (you'll need them later):
   - Gateway URL
   - Client ID
   - Client Secret
   - Token URL

## Deployment

### Method 1: Automated Deployment Script (Recommended)

The automated script handles BDA project creation and CDK deployment:

1. Clone the repository:
```bash
git clone [INSERT_REPOSITORY_URL]
cd patent-novelty-assessment
```

2. Make the deployment script executable:
```bash
chmod +x deploy.sh
```

3. Run the deployment script:
```bash
./deploy.sh
```

The script will:
- Detect your AWS region
- Use the hardcoded BDA project ARN (for development)
- Install Node.js dependencies
- Deploy the CDK stack
- Output resource ARNs and next steps

4. **Note down the following outputs** from the deployment:
   - S3 Bucket Name
   - Docker Image URI (for Agent Core Runtime)
   - IAM Role ARN (for Agent Core Runtime)
   - DynamoDB Table Names

### Method 2: Manual CDK Deployment

If you prefer manual control:

1. Clone the repository:
```bash
git clone [INSERT_REPOSITORY_URL]
cd patent-novelty-assessment
```

2. Navigate to backend directory:
```bash
cd backend
```

3. Install dependencies:
```bash
npm install
```

4. Set BDA Project ARN (use existing or create new):
```bash
# Option A: Use existing BDA project
export BDA_PROJECT_ARN="arn:aws:bedrock:us-west-2:216989103356:data-automation-project/97146aaabae2"

# Option B: Create new BDA project
aws bedrock-data-automation create-data-automation-project \
    --project-name "patent-novelty-bda-$(date +%Y%m%d-%H%M%S)" \
    --standard-output-configuration '{
        "document": {
            "extraction": {
                "granularity": {
                    "types": ["DOCUMENT", "PAGE", "ELEMENT"]
                },
                "boundingBox": {
                    "state": "ENABLED"
                }
            },
            "generativeField": {
                "state": "DISABLED"
            },
            "outputFormat": {
                "textFormat": {
                    "types": ["PLAIN_TEXT", "MARKDOWN"]
                },
                "additionalFileFormat": {
                    "state": "ENABLED"
                }
            }
        }
    }' \
    --region us-west-2
```

5. Deploy CDK stack:
```bash
npx cdk deploy --require-approval never --context bdaProjectArn="$BDA_PROJECT_ARN"
```

6. **Note down the CloudFormation outputs** displayed after deployment.

## Post-Deployment Configuration

### 1. Create Agent Core Runtime

The Agent Core Runtime must be created manually in the AWS Console:

1. Go to AWS Console → Amazon Bedrock → Agent Core
2. Click "Create Runtime"
3. Configure runtime:
   - **Runtime Name**: `PatentNoveltyOrchestrator`
   - **Runtime Type**: Container
   - **Container Image URI**: Use the Docker Image URI from deployment outputs
   - **IAM Role**: Use the IAM Role ARN from deployment outputs
   - **Memory**: 2048 MB (recommended)
   - **Timeout**: 900 seconds (15 minutes)
4. Click "Create Runtime"
5. **Copy the Runtime ARN** (format: `arn:aws:bedrock-agentcore:REGION:ACCOUNT:runtime/RUNTIME-ID`)

### 2. Configure Environment Variables

In the Agent Core Runtime configuration, add the following environment variables:

**Required Environment Variables:**

| Variable Name | Value | Source |
|--------------|-------|--------|
| `AWS_REGION` | `us-west-2` (or your region) | Your AWS region |
| `BUCKET_NAME` | `patent-novelty-pdf-processing-ACCOUNT_ID` | From deployment outputs |
| `KEYWORDS_TABLE_NAME` | `patent-keywords-ACCOUNT_ID` | From deployment outputs |
| `RESULTS_TABLE_NAME` | `patent-search-results-ACCOUNT_ID` | From deployment outputs |
| `ARTICLES_TABLE_NAME` | `scholarly-articles-results-ACCOUNT_ID` | From deployment outputs |
| `COMMERCIAL_ASSESSMENT_TABLE_NAME` | `early-commercial-assessment-ACCOUNT_ID` | From deployment outputs |
| `PATENTVIEW_CLIENT_ID` | Your PatentView Gateway Client ID | From Pre-Deployment Step 5 |
| `PATENTVIEW_CLIENT_SECRET` | Your PatentView Gateway Client Secret | From Pre-Deployment Step 5 |
| `PATENTVIEW_TOKEN_URL` | Your PatentView Gateway Token URL | From Pre-Deployment Step 5 |
| `PATENTVIEW_GATEWAY_URL` | Your PatentView Gateway URL | From Pre-Deployment Step 5 |
| `SEMANTIC_SCHOLAR_CLIENT_ID` | Your Semantic Scholar Gateway Client ID | From Pre-Deployment Step 6 |
| `SEMANTIC_SCHOLAR_CLIENT_SECRET` | Your Semantic Scholar Gateway Client Secret | From Pre-Deployment Step 6 |
| `SEMANTIC_SCHOLAR_TOKEN_URL` | Your Semantic Scholar Gateway Token URL | From Pre-Deployment Step 6 |
| `SEMANTIC_SCHOLAR_GATEWAY_URL` | Your Semantic Scholar Gateway URL | From Pre-Deployment Step 6 |

### 3. Update Agent Runtime ARN

Update the Lambda function with the correct Agent Runtime ARN:

1. Open `backend/infrastructure/patent-novelty-stack.ts`
2. Find the `AGENT_RUNTIME_ARN` environment variable (around line 150)
3. Replace the placeholder ARN with your actual Runtime ARN from Step 1
4. Save the file

### 4. Redeploy Stack

Redeploy the CDK stack to update the Lambda function:

```bash
cd backend
npx cdk deploy --require-approval never --context bdaProjectArn="$BDA_PROJECT_ARN"
```

## Verification

Test the deployment:

1. **Upload a test PDF**:
```bash
aws s3 cp test-invention.pdf s3://patent-novelty-pdf-processing-ACCOUNT_ID/uploads/
```

2. **Monitor Lambda logs**:
```bash
# Check PDF processor logs
aws logs tail /aws/lambda/PatentNoveltyStack-PdfProcessorFunction --follow

# Check agent trigger logs
aws logs tail /aws/lambda/PatentNoveltyStack-AgentTriggerFunction --follow
```

3. **Check DynamoDB tables**:
```bash
# Check keywords table
aws dynamodb scan --table-name patent-keywords-ACCOUNT_ID --limit 5

# Check patent results table
aws dynamodb scan --table-name patent-search-results-ACCOUNT_ID --limit 5
```

4. **Download generated reports**:
```bash
aws s3 ls s3://patent-novelty-pdf-processing-ACCOUNT_ID/reports/
aws s3 cp s3://patent-novelty-pdf-processing-ACCOUNT_ID/reports/test-invention_report.pdf ./
```

## Troubleshooting

**Issue: BDA processing fails**
- Verify BDA project ARN is correct
- Check Lambda execution role has `bedrock:InvokeDataAutomationAsync` permission
- Ensure PDF is valid and not corrupted

**Issue: Agent Core invocation fails**
- Verify Agent Runtime ARN is correct in Lambda environment variable
- Check Lambda execution role has `bedrock-agentcore:InvokeAgentRuntime` permission
- Verify Agent Core Runtime is in "Active" state

**Issue: PatentView/Semantic Scholar searches fail**
- Verify all gateway environment variables are set correctly in Agent Core Runtime
- Check OAuth credentials are valid
- Test gateway connectivity from AWS Console

**Issue: DynamoDB write errors**
- Verify Agent Core Runtime IAM role has DynamoDB write permissions
- Check table names match environment variables exactly
- Ensure tables exist in the correct region

**Issue: Docker image build fails**
- Verify Docker is running: `docker ps`
- Check available disk space
- Ensure you have permissions to push to ECR

**Issue: CDK deployment fails**
- Run `npx cdk bootstrap` if this is your first CDK deployment in the region
- Verify AWS credentials are configured correctly
- Check CloudFormation console for detailed error messages

For additional support, check CloudWatch Logs for detailed error messages from Lambda functions and Agent Core Runtime.
