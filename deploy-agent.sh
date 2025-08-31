#!/bin/bash

set -e

echo "Deploying Patent Novelty Agent..."

# Step 1: Install dependencies
echo "Installing dependencies..."
npm install

# Step 2: Build TypeScript
echo "Building TypeScript..."
npm run build

# Step 3: Deploy agent stack
echo "Deploying agent stack..."
npm run deploy-agent

echo "Deployment completed!"
echo ""
echo "Next steps:"
echo "1. Go to AWS Console > Bedrock > Agent Core"
echo "2. Create new Agent Runtime using the Docker image URI from the output"
echo "3. Use the IAM Role ARN from the output"
echo "4. Set environment variables:"
echo "   - AWS_REGION: us-west-2"
echo "   - BUCKET_NAME: [from output]"
