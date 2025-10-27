# Patent Novelty Assessment System - Deployment Guide

This guide provides step-by-step instructions to deploy the Patent Novelty Assessment System in your AWS account. The deployment is done entirely through the AWS Console and CloudShell.

**Estimated Time:** 30-45 minutes

**Prerequisites:**

- AWS Account with appropriate permissions
- Access to AWS Console
- Basic familiarity with AWS services

---

## Deployment Overview

The deployment consists of 3 main phases:

1. **Phase 1:** Create API Identities and Gateways (PatentView & Semantic Scholar)
2. **Phase 2:** Create and Configure Agent Runtime
3. **Phase 3:** Deploy Infrastructure via CloudShell

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

## Phase 2: Create and Configure Agent Runtime

### Step 2.1: Create Agent Runtime

1. In **Agent Core** → **Agent runtime**, click **Host agent**
2. **Basic Configuration:**
   - **Name:** `Patent-Novelty-Agent`
   - **Description:** `Multi-agent orchestrator for patent novelty assessment`
3. **Container Image:**
   - Select **any existing Docker image** in your ECR (we'll update this later)
   - If you don't have any, use: `public.ecr.aws/docker/library/python:3.12-slim`
4. **Keep all other settings as default**

### Step 2.2: Configure Environment Variables (Part 1)

1. Scroll to **Advanced Configurations**
2. Click **Add environment variable**
3. Add the following **9 environment variables** one by one:

```bash
# Gateway Credentials (from Phase 1)
PATENTVIEW_CLIENT_ID=<your_value>
PATENTVIEW_CLIENT_SECRET=<your_value>
PATENTVIEW_TOKEN_URL=<your_value>
PATENTVIEW_GATEWAY_URL=<your_value>

SEMANTIC_SCHOLAR_CLIENT_ID=<your_value>
SEMANTIC_SCHOLAR_CLIENT_SECRET=<your_value>
SEMANTIC_SCHOLAR_TOKEN_URL=<your_value>
SEMANTIC_SCHOLAR_GATEWAY_URL=<your_value>

# AWS Region (use the region you're deploying in)
AWS_REGION=<your_region>
```

**Important:** Replace `<your_value>` with the actual values you copied in Phase 1.

### Step 2.3: Save Agent Runtime ARN

1. Click **Host Agent**
2. Wait for the agent to be created (this may take a few minutes)
3. Once created, **copy the Agent Runtime ARN**
   - Format: `arn:aws:bedrock-agentcore:REGION:ACCOUNT:runtime/RUNTIME-ID`
4. **Save this ARN** - you'll need it in Phase 3

**Note:** The agent will show as "Unhealthy" initially - this is expected. We'll update it after deploying the infrastructure.

---

## Phase 3: Deploy Infrastructure via CloudShell

### Step 3.1: Open AWS CloudShell

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

### Step 3.2: Clone the Repository

```bash
git clone https://github.com/ASUCICREPO/patent-novelty-assessment.git
cd patent-novelty-assessment
```

### Step 3.3: Make Deploy Script Executable

```bash
chmod +x ./deploy.sh
```

### Step 3.4: Run Deployment Script

```bash
./deploy.sh
```

### Step 3.5: Provide Agent Runtime ARN

When prompted:

```
Enter your Agent Runtime ARN:
```

Paste the **Agent Runtime ARN** you saved in Step 2.3.

### Step 3.6: Wait for Deployment

The deployment will:

1. Create BDA (Bedrock Data Automation) project
2. Create IAM service role
3. Create Amplify application
4. Create CodeBuild project
5. Deploy CDK stack (backend infrastructure)
6. Deploy frontend to Amplify

**This will take approximately 15-20 minutes.**

### Step 3.7: Extract Environment Variables

When deployment completes, you'll see CDK outputs. **Copy and save these 5 values:**

```bash
BUCKET_NAME=patent-novelty-pdf-processing-<account-id>
KEYWORDS_TABLE_NAME=patent-keywords-<account-id>
RESULTS_TABLE_NAME=patent-search-results-<account-id>
ARTICLES_TABLE_NAME=scholarly-articles-results-<account-id>
COMMERCIAL_ASSESSMENT_TABLE_NAME=early-commercial-assessment-<account-id>
```

Also note the **API Gateway URL** and **Frontend URL** from the deployment summary.

---

## Phase 4: Update Agent Runtime Configuration

### Step 4.1: Add Remaining Environment Variables

1. Go back to **Agent Core** → **Agent runtime**
2. Select your `Patent-Novelty-Agent`
3. Click **Edit**
4. Scroll to **Advanced Configurations** → **Environment variables**
5. Add the following **5 environment variables** (from Step 3.7):

```bash
BUCKET_NAME=<value_from_deployment>
KEYWORDS_TABLE_NAME=<value_from_deployment>
RESULTS_TABLE_NAME=<value_from_deployment>
ARTICLES_TABLE_NAME=<value_from_deployment>
COMMERCIAL_ASSESSMENT_TABLE_NAME=<value_from_deployment>
```

### Step 4.2: Update Container Image

1. Still in the Edit screen, scroll to **Container image**
2. Replace with the **Docker Image URI** from the CDK outputs:
   ```
   <account-id>.dkr.ecr.<region>.amazonaws.com/cdk-hnb659fds-container-assets-<account-id>-<region>:<hash>
   ```
3. Click **Save changes**

### Step 4.3: Host the Agent

1. Click **Host agent**
2. Wait for the agent to become **Healthy** (this may take 2-3 minutes)
3. Once healthy, the agent is ready to use

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
3. IAM permissions not propagated

**Solution:**

1. Verify all 14 environment variables are set correctly
2. Ensure Docker image URI matches the CDK output
3. Wait 2-3 minutes for IAM permissions to propagate
4. Check CloudWatch Logs for detailed error messages

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
