# Prerequisites

Before deploying the Patent Novelty Assessment System, ensure you have the following prerequisites in place.

## AWS Account Requirements

### 1. AWS Account Access

You need an AWS account with appropriate permissions to create and manage the following services:

- **Amazon S3** - Object storage for documents and reports
- **AWS Lambda** - Serverless compute functions
- **Amazon DynamoDB** - NoSQL database tables
- **Amazon API Gateway** - RESTful API endpoints
- **AWS IAM** - Identity and access management roles and policies
- **Amazon ECR** - Container registry for Docker images
- **AWS Amplify** - Frontend hosting
- **AWS CodeBuild** - CI/CD pipeline

### 2. Amazon Bedrock Access

Your AWS account must have access to the following Amazon Bedrock services:

#### Bedrock Data Automation (BDA)
- **Purpose**: Automated PDF text extraction and document processing
- **Required Permissions**: 
  - `bedrock:CreateDataAutomationProject`
  - `bedrock:InvokeDataAutomationAsync`
  - `bedrock:GetDataAutomationStatus`
- **How to Request Access**: 
  - Navigate to the [Amazon Bedrock console](https://console.aws.amazon.com/bedrock/)
  - Request access to Bedrock Data Automation in your AWS region
  - Wait for approval (typically instant for supported regions)

#### Bedrock Agent Core
- **Purpose**: Multi-agent orchestration and runtime hosting
- **Required Permissions**:
  - `bedrock-agentcore:CreateAgentRuntime`
  - `bedrock-agentcore:InvokeAgentRuntime`
- **How to Request Access**:
  - Navigate to the [Amazon Bedrock console](https://console.aws.amazon.com/bedrock/)
  - Go to **Agent Core** → **Agent runtime**
  - Ensure you can access the "Host agent" functionality
  - If not available, contact AWS support to enable Agent Core in your account

#### Claude Sonnet 4.5 Model Access
- **Model ID**: `global.anthropic.claude-sonnet-4-5-20250929-v1:0`
- **Purpose**: Large language model for AI analysis and evaluation
- **How to Request Access**:
  - Navigate to the [Amazon Bedrock console](https://console.aws.amazon.com/bedrock/)
  - Go to **Model access**
  - Request access to **Claude Sonnet 4.5** (Anthropic)
  - Wait for approval (typically instant)

---

## External API Keys

The system integrates with two external APIs for patent and academic literature searches. You must request API keys for both services before deployment.

### 1. PatentView API Key

**Purpose**: Access to USPTO patent database for prior art searches

**Request API Key**:
1. Visit the PatentView API Key Request Portal:
   - **URL**: https://patentsview-support.atlassian.net/servicedesk/customer/portal/1/group/1/create/18
2. Fill out the API key request form
3. Provide your:
   - Name
   - Email address
   - Organization
   - Intended use case (e.g., "Patent novelty assessment and prior art search")
4. Submit the request
5. Wait for approval (typically 1-3 business days)
6. You will receive your API key via email

**What You'll Receive**:
- API Key (used in `X-Api-Key` header)
- Rate limits and usage guidelines

### 2. Semantic Scholar API Key

**Purpose**: Access to 200M+ academic papers for literature searches

**Request API Key**:
1. Visit the Semantic Scholar API Portal:
   - **URL**: https://www.semanticscholar.org/product/api
2. Click **"Get API Key"** or **"Request API Access"**
3. Sign up or log in with your account
4. Fill out the API access request form
5. Provide your:
   - Name
   - Email address
   - Organization/Institution
   - Research purpose (e.g., "Patent prior art search and academic literature analysis")
6. Submit the request
7. Wait for approval (typically instant to 1 business day)
8. You will receive your API key via email or in your account dashboard

**What You'll Receive**:
- API Key (used in `x-api-key` header)
- Rate limits (typically 100 requests per 5 minutes with API key)

---

## AWS Region Considerations

The system can be deployed in any AWS region that supports:
- Amazon Bedrock with Claude Sonnet 4.5
- Amazon Bedrock Data Automation
- Amazon Bedrock Agent Core

**Recommended Regions**:
- `us-east-1` (US East - N. Virginia)
- `us-west-2` (US West - Oregon)

**Note**: Ensure all services are available in your chosen region before deployment.

---

## Cost Considerations

Before deployment, review the [Cost Estimation Guide](./costEstimation.md) to understand:
- Per-invention processing costs (~$0.83)
- Monthly infrastructure costs (~$0.22)
- AWS Free Tier eligibility

---

## Support

For questions or issues with prerequisites:
- **AWS Services**: Contact AWS Support or consult AWS documentation
- **PatentView API**: Use the PatentView support portal
- **Semantic Scholar API**: Contact Semantic Scholar support via their website
- **Deployment Issues**: Refer to the [Deployment Guide](./deploymentGuide.md) troubleshooting section
