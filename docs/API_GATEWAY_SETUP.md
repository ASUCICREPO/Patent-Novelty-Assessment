# API Gateway Setup Guide

This guide explains how to deploy and configure the Patent Novelty Assessment application to use AWS API Gateway instead of Next.js API routes.

## Overview

The application has been updated to use AWS API Gateway with Lambda functions for all backend operations:

- **S3 Operations**: File uploads, presigned URL generation, report status checks
- **DynamoDB Operations**: Querying and updating patent analysis results, search results
- **Agent Invocations**: Triggering Bedrock Agent Core for patent searches, scholarly searches, and report generation

## Architecture

```
Frontend (Next.js) → API Gateway → Lambda Functions → AWS Services (S3, DynamoDB, Bedrock)
```

## Deployment Steps

### 1. Deploy the API Gateway Infrastructure

```bash
# Make the deployment script executable
chmod +x deploy.sh

# Deploy the CDK stack
./deploy.sh
```

This will create:
- API Gateway REST API with CORS enabled
- Three Lambda functions (S3, DynamoDB, Agent Invoke)
- IAM roles with proper permissions
- All necessary AWS resources

### 2. Get the API Gateway URL

After deployment, the script will output the API Gateway URL. It will look like:
```
https://your-api-id.execute-api.us-west-2.amazonaws.com/prod
```

### 3. Configure the Frontend

Create a `.env.local` file in the frontend directory:

```bash
# Copy the example environment file
cp env.example .env.local

# Edit the file and set your API Gateway URL
NEXT_PUBLIC_API_BASE_URL=https://your-api-id.execute-api.us-west-2.amazonaws.com/prod
```

### 4. No Additional Configuration Required

**Note**: All AWS service interactions are now handled through the API Gateway endpoints. You don't need to configure individual DynamoDB table names, S3 bucket names, Bedrock Agent ARNs, or other AWS resource identifiers in the frontend - these are all managed by the backend Lambda functions.

### 5. Start the Frontend

```bash
cd frontend
npm install
npm run dev
```

## API Endpoints

The API Gateway provides the following endpoints:

### S3 Operations
- `POST /s3` - Upload files (now uses presigned URLs for direct S3 upload)
- `GET /s3?operation=get_presigned_url&filename=<filename>` - Get presigned URL for direct S3 upload
- `GET /s3?operation=get_signed_urls&filename=<filename>` - Get signed URLs for reports
- `GET /s3?operation=check_reports&filename=<filename>` - Check if reports are ready

### DynamoDB Operations
- `GET /dynamodb?tableType=patent-results&pdfFilename=<filename>` - Query patent search results
- `GET /dynamodb?tableType=scholarly-results&pdfFilename=<filename>` - Query scholarly article results
- `GET /dynamodb?tableType=analysis&fileName=<filename>` - Get analysis results
- `PUT /dynamodb` - Update records (keywords, add_to_report flags)

### Agent Invoke Operations
- `POST /agent-invoke` - Trigger Bedrock Agent operations
  - Actions: `search_patents`, `search_articles`, `generate_report`

## Configuration

The frontend uses a centralized configuration system in `lib/config.ts`:

- `getApiUrl(endpoint)` - Get full API URL for any endpoint
- `getS3ApiUrl()` - Get S3 API URL
- `getDynamoDBApiUrl()` - Get DynamoDB API URL
- `getAgentInvokeApiUrl()` - Get Agent Invoke API URL

## Fallback Behavior

If `NEXT_PUBLIC_API_BASE_URL` is not set, the application will fall back to using relative paths (`/api/...`) for development purposes.

## Troubleshooting

### Common Issues

1. **CORS Errors**: The API Gateway is configured with CORS enabled for all origins. If you encounter CORS issues, check that the API Gateway deployment completed successfully.

2. **API Gateway URL**: Verify that the API Gateway URL is correct and accessible in your `.env.local` file.

3. **File Upload Issues**: If file uploads fail, check that the presigned URL generation is working correctly.

### Testing the API

You can test the API endpoints directly:

```bash
# Test presigned URL generation for file upload
curl "https://your-api-id.execute-api.us-west-2.amazonaws.com/prod/s3?operation=get_presigned_url&filename=test.pdf"

# Test DynamoDB query for patent results
curl "https://your-api-id.execute-api.us-west-2.amazonaws.com/prod/dynamodb?tableType=patent-results&pdfFilename=test.pdf"

# Test DynamoDB query for analysis results
curl "https://your-api-id.execute-api.us-west-2.amazonaws.com/prod/dynamodb?tableType=analysis&fileName=test"

# Test agent invoke
curl -X POST https://your-api-id.execute-api.us-west-2.amazonaws.com/prod/agent-invoke \
  -H "Content-Type: application/json" \
  -d '{"action": "search_patents", "pdfFilename": "test.pdf"}'
```

## File Upload Process

The application now uses a two-step process for file uploads to avoid API Gateway binary data corruption:

1. **Request Presigned URL**: Frontend requests a presigned S3 URL from the API Gateway
2. **Direct S3 Upload**: Frontend uploads the file directly to S3 using the presigned URL

This approach ensures files are uploaded without corruption and bypasses API Gateway's binary data handling limitations.

## Benefits of API Gateway

1. **Scalability**: Lambda functions auto-scale based on demand
2. **Security**: No AWS credentials exposed to the frontend
3. **Monitoring**: Built-in CloudWatch logging and metrics
4. **Cost**: Pay only for actual usage
5. **Reliability**: AWS-managed infrastructure with high availability
6. **File Integrity**: Direct S3 uploads prevent binary data corruption

## Next Steps

1. Deploy the API Gateway infrastructure
2. Update your frontend configuration
3. Test the application end-to-end
4. Monitor the Lambda functions in CloudWatch
5. Set up proper error handling and retry logic if needed
