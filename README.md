# Patent Novelty PDF Processing Pipeline

A serverless pipeline that automatically processes PDF files uploaded to S3 using AWS Bedrock Data Automation (BDA) to extract text and images in JSON format.

## Architecture

- **S3 Bucket**: Stores uploaded PDFs and processed outputs
- **Lambda Function**: Triggered by S3 events to invoke BDA processing
- **Bedrock Data Automation**: Extracts text and images from PDFs
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

## Deployment

1. **Quick Deploy**:
   ```bash
   ./backend/scripts/deploy.sh
   ```

2. **Manual Steps**:
   ```bash
   # Create BDA project
   ./backend/scripts/create-bda-project.sh
   
   # Install dependencies
   npm install
   
   # Deploy infrastructure
   npx cdk deploy
   ```

## Usage

1. Upload a PDF file to the `uploads/` folder in your S3 bucket
2. The Lambda function will automatically trigger
3. BDA processes the PDF and outputs JSON to `temp/docParser/`
4. Temporary files are stored in `temp/temporary/`

## Monitoring

Check CloudWatch logs for the Lambda function to monitor processing status and debug any issues.

## Clean Up

```bash
npx cdk destroy
```
