#!/bin/bash

set -e

echo "Starting Patent Novelty Pipeline deployment..."

# Get AWS region dynamically
REGION=$(aws configure get region 2>/dev/null || echo "us-west-2")
echo "Using AWS region: $REGION"

# Use hardcoded BDA project ARN for development
BDA_PROJECT_ARN="arn:aws:bedrock:us-west-2:216989103356:data-automation-project/97146aaabae2"
echo "Using hardcoded BDA Project ARN: $BDA_PROJECT_ARN"

# TODO: Uncomment below for production deployment (creates new BDA project each time)
# Create BDA project with unique name
# BDA_PROJECT_NAME="patent-novelty-bda-$(date +%Y%m%d-%H%M%S)"
# 
# echo "Creating BDA project: $BDA_PROJECT_NAME"
# BDA_RESPONSE=$(aws bedrock-data-automation create-data-automation-project \
#     --project-name "$BDA_PROJECT_NAME" \
#     --standard-output-configuration '{
#         "document": {
#             "extraction": {
#                 "granularity": {
#                     "types": ["DOCUMENT", "PAGE", "ELEMENT"]
#                 },
#                 "boundingBox": {
#                     "state": "ENABLED"
#                 }
#             },
#             "generativeField": {
#                 "state": "DISABLED"
#             },
#             "outputFormat": {
#                 "textFormat": {
#                     "types": ["PLAIN_TEXT", "MARKDOWN"]
#                 },
#                 "additionalFileFormat": {
#                     "state": "ENABLED"
#                 }
#             }
#         }
#     }' \
#     --region $REGION 2>/dev/null || {
#     echo "Error: Failed to create BDA project"
#     exit 1
# })
# 
# BDA_PROJECT_ARN=$(echo $BDA_RESPONSE | jq -r '.projectArn')
# 
# if [ -z "$BDA_PROJECT_ARN" ]; then
#     echo "Error: Failed to create BDA project"
#     exit 1
# fi
# 
# echo "Created BDA Project ARN: $BDA_PROJECT_ARN"

# Change to backend directory
echo "Changing to backend directory..."
cd backend

# Install dependencies
echo "Installing dependencies..."
npm install

# Deploy CDK stack
echo "Deploying CDK stack..."
npx cdk deploy --require-approval never --context bdaProjectArn="$BDA_PROJECT_ARN"

# Get the API Gateway URL
echo "Getting API Gateway URL..."
API_URL=$(aws cloudformation describe-stacks \
    --stack-name PatentNoveltyStack \
    --query 'Stacks[0].Outputs[?OutputKey==`ApiGatewayUrl`].OutputValue' \
    --output text)

# Return to root directory
cd ..

echo ""
echo "✅ Deployment completed successfully!"
echo ""
echo "🌐 API Gateway URL: $API_URL"
echo ""
echo "📚 Available endpoints:"
echo "   POST $API_URL/s3          - File upload"
echo "   GET  $API_URL/s3          - Get signed URLs / Check reports"
echo "   GET  $API_URL/dynamodb    - Query DynamoDB"
echo "   PUT  $API_URL/dynamodb    - Update DynamoDB"
echo "   POST $API_URL/agent-invoke - Invoke Bedrock Agent"
echo ""
echo "🔧 Frontend Configuration:"
echo "   Add to your frontend .env.local file:"
echo "   NEXT_PUBLIC_API_BASE_URL=$API_URL"
echo ""
echo "📋 Next steps:"
echo "1. Go to AWS Console > Bedrock > Agent Core"
echo "2. Create new Agent Runtime using the Patent Orchestrator Docker image URI from the output"
echo "3. Use the Patent Orchestrator IAM Role ARN from the output"
echo "4. Configure environment variables for USPTO and Crossref gateways in Agent Core"
echo "5. Update the AGENT_RUNTIME_ARN in the CDK stack with the correct runtime ARN"
echo "6. Redeploy: npx cdk deploy"
echo ""
echo "📖 For more information, see API_GATEWAY_SETUP.md"
