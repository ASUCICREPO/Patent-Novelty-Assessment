# Patent Novelty PDF Processing Pipeline

A serverless pipeline that automatically processes PDF files uploaded to S3 using AWS Bedrock Data Automation (BDA) to extract text and images, then generates patent search keywords using a Strands Agent.

## Architecture

- **S3 Bucket**: Stores uploaded PDFs and processed outputs
- **Lambda Function (PDF Processor)**: Triggered by S3 events to invoke BDA processing
- **Lambda Function (Agent Trigger)**: Triggered when BDA completes to invoke Agent Core
- **Bedrock Data Automation**: Extracts text and images from PDFs
- **Agent Core Runtime**: Runs Strands Agent to generate patent search keywords
- **CDK**: Infrastructure as Code for deployment

## Folder Structure

```
uploads/          # Upload PDF files here
temp/
  ├── docParser/  # JSON outputs from BDA
  └── temporary/  # Temporary BDA processing files
```

## Prerequisites

- AWS CLI configured with appropriate permissions
- Node.js 18+ and npm
- CDK CLI installed (`npm install -g aws-cdk`)
- Access to AWS Bedrock Data Automation service
- Access to AWS Bedrock Agent Core service

## Deployment

**One-Command Deployment**:
```bash
./deploy.sh
```

This script will:
1. Check if BDA project exists, create one if needed
2. Install all dependencies
3. Build Lambda functions
4. Deploy the complete infrastructure

**Manual Steps After Deployment**:
1. Go to AWS Console > Bedrock > Agent Core
2. Create new Agent Runtime using the Docker image URI from CDK output
3. Use the IAM Role ARN from CDK output
4. Update the `AGENT_RUNTIME_ARN` in the CDK stack
5. Redeploy: `npx cdk deploy`

## Usage

1. Upload a PDF file to the `uploads/` folder in your S3 bucket
2. The PDF processor Lambda function will automatically trigger BDA processing
3. BDA processes the PDF and outputs JSON to `temp/docParser/`
4. The agent trigger Lambda function automatically detects the BDA completion
5. Agent Core is invoked to generate patent search keywords
6. Results are processed and logged

## Automated Pipeline Flow

```
PDF Upload → BDA Processing → result.json → Agent Trigger → Keyword Generation
```

## Monitoring

- Check CloudWatch logs for both Lambda functions to monitor processing status
- Use Agent Core observability features to view agent execution details
- Monitor S3 bucket for BDA processing outputs

## Clean Up

```bash
npx cdk destroy
```

## Environment Variables

### PDF Processor Lambda
- `BUCKET_NAME`: S3 bucket name
- `BDA_PROJECT_ARN`: Bedrock Data Automation project ARN

### Agent Trigger Lambda  
- `AGENT_RUNTIME_ARN`: Agent Core runtime ARN (format: `arn:aws:bedrock-agentcore:REGION:ACCOUNT:runtime/RUNTIME-ID`)