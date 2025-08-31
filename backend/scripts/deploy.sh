#!/bin/bash

set -e

echo "Starting deployment process..."

# Step 1: Create BDA project if ARN file doesn't exist
if [ ! -f "backend/scripts/bda-project-arn.txt" ]; then
    echo "Creating BDA project..."
    ./backend/scripts/create-bda-project.sh
fi

# Step 2: Read BDA project ARN
BDA_PROJECT_ARN=$(cat backend/scripts/bda-project-arn.txt)
echo "Using BDA Project ARN: $BDA_PROJECT_ARN"

# Step 3: Install dependencies
echo "Installing dependencies..."
npm install

# Step 4: Build Lambda function
echo "Building Lambda function..."
cd backend/lambda/pdf-processor
npm install
npx tsc index.ts --target ES2020 --module commonjs --outDir . --skipLibCheck
cd ../../..

# Step 5: Deploy CDK stack
echo "Deploying CDK stack..."
npx cdk bootstrap
npx cdk deploy --require-approval never

# Step 6: Update Lambda environment variable with BDA ARN
echo "Updating Lambda function with BDA Project ARN..."
FUNCTION_NAME=$(aws cloudformation describe-stacks \
    --stack-name PatentNoveltyPdfProcessingStack \
    --query 'Stacks[0].Outputs[?OutputKey==`LambdaFunctionName`].OutputValue' \
    --output text)

aws lambda update-function-configuration \
    --function-name $FUNCTION_NAME \
    --environment Variables="{BUCKET_NAME=$(aws cloudformation describe-stacks --stack-name PatentNoveltyPdfProcessingStack --query 'Stacks[0].Outputs[?OutputKey==`BucketName`].OutputValue' --output text),BDA_PROJECT_ARN=$BDA_PROJECT_ARN}"

echo "Deployment completed successfully!"
echo "Upload PDF files to the 'uploads/' folder in your S3 bucket to trigger processing."
