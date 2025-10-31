# Patent Novelty Assessment System - Deployment Guide

This guide provides step-by-step instructions to deploy the Patent Novelty Assessment System in your AWS account. The deployment is done entirely through the AWS Console and CloudShell.

**Estimated Time:** 30-45 minutes

**Prerequisites:**

- AWS Account with appropriate permissions
- Access to AWS Console
- Basic familiarity with AWS services

---

## Deployment Overview

The deployment consists of 4 main phases:

1. **Phase 1:** Create API Identities and Gateways (PatentView & Semantic Scholar)
2. **Phase 2:** Deploy Infrastructure via CloudShell
3. **Phase 3:** Create and Configure Agent Runtime
4. **Phase 4:** Update Lambda Functions

---

## Phase 1: Create API Identities and Gateways

### Step 1.1: Create PatentView API Identity

1. Navigate to **Amazon Bedrock** in AWS Console
2. In the left sidebar, go to **Agent Core** → **Identity**
3. Click **Add API Key**
4. Configure:
   - **Name:** `patent-view`
   - Click **Add**
5. **Save the API Key** - you'll need it later

### Step 1.2: Create Semantic Scholar API Identity

1. Still in **Agent Core** → **Identity**
2. Click **Add API Key**
3. Configure:
   - **Name:** `semantic-scholar`
   - Click **Add**
4. **Save the API Key** - you'll need it later

### Step 1.3: Create PatentView Gateway

1. In the left sidebar, go to **Agent Core** → **Gateway**
2. Click **Create gateway**
3. **Basic Configuration:**
   - **Name:** `patent-search`
   - **Description:** `Gateway for PatentView USPTO patent database API`
4. **Additional Settings:**
   - ✅ Enable **Semantic search**
   - ✅ Enable **Exception level debug**
5. **Inbound Auth Configuration:**
   - Select **Use JSON Web Token**
   - Click **Quick create**
   - Select **IAM permission**
   - Click **Create new**
6. **Target Configuration:**
   - **Target:** Select `patent-view` (the identity you created)
   - **Type:** `REST API`
   - **OpenAPI Schema:** Select `Define an inline schema`
   - Copy the contents from `docs/patentview_openapi_spec.json` in the GitHub repository
   - Paste into the schema editor
7. **API Key Configuration:**
   - Select **API key option**
   - Select `patent-view` API key
8. **Additional Configuration:**
   - **Header:** `X-Api-Key`
9. Click **Create gateway**

### Step 1.4: Copy PatentView Gateway Credentials

1. After gateway creation, expand **View invocation code**
2. **Copy and save these values:**
   ```
   PATENTVIEW_CLIENT_ID=<value>
   PATENTVIEW_CLIENT_SECRET=<value>
   PATENTVIEW_TOKEN_URL=<value>
   PATENTVIEW_GATEWAY_URL=<value>
   ```
3. To get Client ID and Secret:
   - Click on the Cognito link in the invocation code
   - Navigate to **Amazon Cognito** → **User pools** → Your pool → **App integration** → **App clients**
   - Copy the **Client ID** and **Client secret**

### Step 1.5: Create Semantic Scholar Gateway

1. In **Agent Core** → **Gateway**, click **Create gateway**
2. **Basic Configuration:**
   - **Name:** `semantic-scholar-search`
   - **Description:** `Gateway for Semantic Scholar academic paper database API`
3. **Additional Settings:**
   - ✅ Enable **Semantic search**
   - ✅ Enable **Exception level debug**
4. **Inbound Auth Configuration:**
   - Select **Use JSON Web Token**
   - Click **Quick create**
   - Select **IAM permission**
   - Click **Create new**
5. **Target Configuration:**
   - **Target:** Select `semantic-scholar` (the identity you created)
   - **Type:** `REST API`
   - **OpenAPI Schema:** Select `Define an inline schema`
   - Copy the contents from `docs/semantic_scholar_openapi_spec.json` in the GitHub repository
   - Paste into the schema editor
6. **API Key Configuration:**
   - Select **API key option**
   - Select `semantic-scholar` API key
7. **Additional Configuration:**
   - **No header needed** (leave empty)
8. Click **Create gateway**

### Step 1.6: Copy Semantic Scholar Gateway Credentials

1. After gateway creation, expand **View invocation code**
2. **Copy and save these values:**
   ```
   SEMANTIC_SCHOLAR_CLIENT_ID=<value>
   SEMANTIC_SCHOLAR_CLIENT_SECRET=<value>
   SEMANTIC_SCHOLAR_TOKEN_URL=<value>
   SEMANTIC_SCHOLAR_GATEWAY_URL=<value>
   ```
3. To get Client ID and Secret:
   - Click on the Cognito link in the invocation code
   - Navigate to **Amazon Cognito** → **User pools** → Your pool → **App integration** → **App clients**
   - Copy the **Client ID** and **Client secret**

### Step 1.7: Verify Gateway Creation

Before proceeding, ensure:

- ✅ Both identities (`patent-view` and `semantic-scholar`) are created
- ✅ Both gateways (`patent-search` and `semantic-scholar-search`) are created
- ✅ You have saved all 8 credential values (4 for each gateway)

---

## Phase 2: Deploy Infrastructure via CloudShell

### Step 2.1: Open AWS CloudShell

1. In the AWS Console, click the **CloudShell icon** (terminal icon in the top navigation bar)
2. Wait for CloudShell to initialize
3. Verify your region:
   ```bash
   echo $AWS_REGION
   ```
   - If it doesn't show your desired region, set it:
   ```bash
   export AWS_REGION=<your_region>
   ```

### Step 2.2: Clone the Repository

```bash
git clone https://github.com/ASUCICREPO/Patent-Novelty-Assessment.git
cd patent-novelty-assessment
```

### Step 2.3: Make Deploy Script Executable

```bash
chmod +x ./deploy.sh
```

### Step 2.4: Run Deployment Script

```bash
./deploy.sh
```

**Note:** The script will NO LONGER prompt for Agent Runtime ARN. The infrastructure will be deployed first, then you'll create the Agent Runtime in Phase 3.

### Step 2.5: Wait for Deployment

The deployment will:

1. Create BDA (Bedrock Data Automation) project
2. Create IAM service role
3. Create Amplify application
4. Create CodeBuild project
5. Deploy CDK stack (backend infrastructure)
6. Deploy frontend to Amplify

**This will take approximately 15-20 minutes.**

### Step 2.6: Extract Environment Variables

When deployment completes, you'll see CDK outputs. **Copy and save these values:**

```bash
BUCKET_NAME=patent-novelty-pdf-processing-<account-id>
KEYWORDS_TABLE_NAME=patent-keywords-<account-id>
RESULTS_TABLE_NAME=patent-search-results-<account-id>
ARTICLES_TABLE_NAME=scholarly-articles-results-<account-id>
COMMERCIAL_ASSESSMENT_TABLE_NAME=early-commercial-assessment-<account-id>
```

Also note:

- **Docker Image URI** (for Agent Runtime)
- **IAM Role Name** (PatentNoveltyStack-PatentNoveltyOrchestratorRole-XXXXX)
- **Lambda Function Names** (AgentTriggerFunctionName and AgentInvokeApiFunctionName)
- **API Gateway URL**
- **Frontend URL**

---

## Phase 3: Create and Configure Agent Runtime

Now that the infrastructure is deployed, create the Agent Runtime with the correct IAM role and all environment variables at once.

### Step 3.1: Navigate to Agent Core

1. Go to **AWS Bedrock Console** → **Agent Core** → **Agent runtime**
2. Click **Host agent**

### Step 3.2: Basic Configuration

- **Name:** `Patent-Novelty-Agent`
- **Description:** `Multi-agent orchestrator for patent novelty assessment`

### Step 3.3: Container Image

Paste the **Docker Image URI** from Phase 2 CDK outputs:

```
<account-id>.dkr.ecr.<region>.amazonaws.com/cdk-hnb659fds-container-assets-<account-id>-<region>:<hash>
```

### Step 3.4: Permissions (CRITICAL)

1. Scroll to **Permissions**
2. Select **Use an existing service role**
3. From the dropdown, choose: `PatentNoveltyStack-PatentNoveltyOrchestratorRole-XXXXX`

**IMPORTANT:** Do NOT use the default `AmazonBedrockAgentCoreRuntimeDefaultServiceRole`. The custom role includes:

- AWS Marketplace permissions for Claude Sonnet 4.5
- S3 access to your processing bucket
- DynamoDB access to all 4 tables
- CloudWatch logging permissions

### Step 3.5: Environment Variables (All 14 at Once)

Scroll to **Advanced Configurations** → **Environment variables** and add all 14 variables:

```bash
# Gateway Credentials (8 variables from Phase 1)
PATENTVIEW_CLIENT_ID=<value_from_phase_1>
PATENTVIEW_CLIENT_SECRET=<value_from_phase_1>
PATENTVIEW_TOKEN_URL=<value_from_phase_1>
PATENTVIEW_GATEWAY_URL=<value_from_phase_1>

SEMANTIC_SCHOLAR_CLIENT_ID=<value_from_phase_1>
SEMANTIC_SCHOLAR_CLIENT_SECRET=<value_from_phase_1>
SEMANTIC_SCHOLAR_TOKEN_URL=<value_from_phase_1>
SEMANTIC_SCHOLAR_GATEWAY_URL=<value_from_phase_1>

# AWS Configuration (1 variable)
AWS_REGION=<your_region>

# Infrastructure Resources (5 variables from Phase 2)
BUCKET_NAME=<value_from_phase_2>
KEYWORDS_TABLE_NAME=<value_from_phase_2>
RESULTS_TABLE_NAME=<value_from_phase_2>
ARTICLES_TABLE_NAME=<value_from_phase_2>
COMMERCIAL_ASSESSMENT_TABLE_NAME=<value_from_phase_2>
```

### Step 3.6: Host the Agent

1. Click **Host agent**
2. Wait for the agent to become **Healthy** (this may take 2-3 minutes)
3. Once healthy, **copy the Agent Runtime ARN**
   - Format: `arn:aws:bedrock-agentcore:REGION:ACCOUNT:runtime/RUNTIME-ID`
4. **Save this ARN** - you'll need it in Phase 4

---

## Phase 4: Update Lambda Functions

The Lambda functions need the Agent Runtime ARN to invoke the agent. Update them now.

### Step 4.1: Update agent_trigger Lambda

```bash
# Set your values
AGENT_ARN="arn:aws:bedrock-agentcore:REGION:ACCOUNT:runtime/XXXXX"
AWS_REGION="your-region"
AGENT_TRIGGER_FUNCTION="<AgentTriggerFunctionName-from-phase-2>"

# Update the Lambda
aws lambda update-function-configuration \
  --function-name $AGENT_TRIGGER_FUNCTION \
  --environment Variables={AGENT_RUNTIME_ARN=$AGENT_ARN} \
  --region $AWS_REGION
```

### Step 4.2: Update agent_invoke_api Lambda

```bash
# Set your values
AGENT_ARN="arn:aws:bedrock-agentcore:REGION:ACCOUNT:runtime/XXXXX"
AWS_REGION="your-region"
FRONTEND_URL="https://main.<amplify-app-id>.amplifyapp.com"
AGENT_INVOKE_FUNCTION="<AgentInvokeApiFunctionName-from-phase-2>"

# Update the Lambda
aws lambda update-function-configuration \
  --function-name $AGENT_INVOKE_FUNCTION \
  --environment Variables={AGENT_RUNTIME_ARN=$AGENT_ARN,ALLOWED_ORIGIN=$FRONTEND_URL} \
  --region $AWS_REGION
```

### Step 4.3: Verify Updates

1. Go to **AWS Lambda Console**
2. Check both Lambda functions
3. Verify the `AGENT_RUNTIME_ARN` environment variable is set correctly

---

## Verification

### Verify Deployment Success

1. **Agent Runtime:** Should show status "Healthy"
2. **Frontend:** Access the Frontend URL from deployment summary
3. **API Gateway:** Should be accessible at the API Gateway URL
4. **S3 Bucket:** Should exist with `uploads/`, `temp/`, and `reports/` folders
5. **DynamoDB Tables:** All 4 tables should be created

### Test the System

1. Navigate to the Frontend URL
2. Upload a test PDF (invention disclosure document)
3. Monitor the processing:
   - Check S3 bucket for uploaded file
   - Check DynamoDB for extracted keywords
   - Trigger patent search via the UI
   - Generate and download reports

---

## Complete Environment Variables Reference

Your Agent Runtime should have **14 environment variables** in total:

```bash
# Gateway Credentials (8 variables)
PATENTVIEW_CLIENT_ID=<value>
PATENTVIEW_CLIENT_SECRET=<value>
PATENTVIEW_TOKEN_URL=<value>
PATENTVIEW_GATEWAY_URL=<value>
SEMANTIC_SCHOLAR_CLIENT_ID=<value>
SEMANTIC_SCHOLAR_CLIENT_SECRET=<value>
SEMANTIC_SCHOLAR_TOKEN_URL=<value>
SEMANTIC_SCHOLAR_GATEWAY_URL=<value>

# AWS Configuration (1 variable)
AWS_REGION=<your_region>

# Infrastructure Resources (5 variables)
BUCKET_NAME=patent-novelty-pdf-processing-<account-id>
KEYWORDS_TABLE_NAME=patent-keywords-<account-id>
RESULTS_TABLE_NAME=patent-search-results-<account-id>
ARTICLES_TABLE_NAME=scholarly-articles-results-<account-id>
COMMERCIAL_ASSESSMENT_TABLE_NAME=early-commercial-assessment-<account-id>
```

---

## Troubleshooting

### Issue: Docker Hub Rate Limit Error

**Error:** `429 Too Many Requests - You have reached your unauthenticated pull rate limit`

**Solution:** The Dockerfile has been updated to use AWS Public ECR. Ensure you have the latest code:

```bash
git pull origin main
```

### Issue: S3 Bucket Region Mismatch

**Error:** `PermanentRedirect: The bucket you are attempting to access must be addressed using the specified endpoint`

**Solution:** Delete old resources from previous region:

```bash
aws cloudformation delete-stack --stack-name PatentNoveltyStack --region <old-region>
aws s3 rb s3://patent-novelty-pdf-processing-<account-id> --force --region <old-region>
```

### Issue: Agent Shows "Unhealthy"

**Possible Causes:**

1. Missing environment variables
2. Incorrect Docker image URI
3. Wrong IAM role selected (using default instead of custom)
4. IAM permissions not propagated

**Solution:**

1. Verify all 14 environment variables are set correctly
2. Ensure Docker image URI matches the CDK output
3. **Verify you selected the custom IAM role** (`PatentNoveltyStack-PatentNoveltyOrchestratorRole-XXX`) not the default
4. Wait 2-3 minutes for IAM permissions to propagate
5. Check CloudWatch Logs for detailed error messages

### Issue: AWS Marketplace Permission Error

**Error:** `User is not authorized to perform: aws-marketplace:ViewSubscriptions`

**Root Cause:** Agent Runtime is using the wrong IAM role (default instead of custom).

**Solution:**

1. The Agent Runtime must be created with the custom IAM role from the start
2. If you already created it with the default role, you must **delete and recreate** the Agent Runtime
3. When recreating, ensure you select: `PatentNoveltyStack-PatentNoveltyOrchestratorRole-XXXXX` in the Permissions section
4. The custom role includes `AmazonBedrockFullAccess` which has the required marketplace permissions

### Issue: Lambda Functions Not Invoking Agent

**Error:** Lambda functions fail when trying to invoke the agent

**Root Cause:** Lambda environment variables not updated with Agent Runtime ARN (Phase 4 not completed).

**Solution:**

1. Verify you completed Phase 4 (Update Lambda Functions)
2. Check Lambda console to confirm `AGENT_RUNTIME_ARN` environment variable is set
3. The value should be your actual Agent Runtime ARN, not `PLACEHOLDER-UPDATE-AFTER-AGENT-CREATION`
4. If still using placeholder, run the update commands from Phase 4

### Issue: Deployment Script Fails

**Solution:**

1. Ensure you're in the correct AWS region
2. Verify you have necessary IAM permissions
3. Check CloudShell has internet connectivity
4. Review CloudWatch Logs for detailed errors

---

## Post-Deployment Configuration

### Configure API Keys

1. **PatentView API Key:**

   - Go to https://patentsview.org/apis/api-endpoints
   - Request an API key
   - Update the `patent-view` identity in Agent Core with your key

2. **Semantic Scholar API Key:**
   - Go to https://www.semanticscholar.org/product/api
   - Request an API key
   - Update the `semantic-scholar` identity in Agent Core with your key

### Set Up Custom Domain (Optional)

1. Go to **AWS Amplify** → Your app
2. Click **Domain management**
3. Add your custom domain
4. Follow the DNS configuration instructions

---

## Clean Up

To delete all resources:

```bash
# Delete CDK stack
aws cloudformation delete-stack --stack-name PatentNoveltyStack

# Delete Amplify app
aws amplify delete-app --app-id <your-app-id>

# Delete Agent Runtime
# (Do this manually in the AWS Console)

# Delete Gateways and Identities
# (Do this manually in the AWS Console)

# Delete BDA project
aws bedrock-data-automation delete-data-automation-project --project-arn <your-project-arn>
```

---

## Support

For issues or questions:

- Check the [Architecture Deep Dive](./architectureDeepDive.md)
- Review the [User Guide](./userGuide.md)
- Check CloudWatch Logs for detailed error messages
- Refer to the [API Documentation](./APIdoc.md)

---

**Deployment Complete!** Your Patent Novelty Assessment System is now ready to use.
