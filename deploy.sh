#!/bin/bash

set -e

echo "Starting Patent Novelty Pipeline deployment..."

# Get AWS region dynamically
REGION=$(aws configure get region 2>/dev/null || echo "us-west-2")
echo "Using AWS region: $REGION"

# Create BDA project with unique name
BDA_PROJECT_NAME="patent-novelty-bda-$(date +%Y%m%d-%H%M%S)"

echo "Creating BDA project: $BDA_PROJECT_NAME"
BDA_RESPONSE=$(aws bedrock-data-automation create-data-automation-project \
    --project-name "$BDA_PROJECT_NAME" \
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
    --region $REGION 2>/dev/null || {
    echo "Error: Failed to create BDA project"
    exit 1
})

BDA_PROJECT_ARN=$(echo $BDA_RESPONSE | jq -r '.projectArn')

if [ -z "$BDA_PROJECT_ARN" ]; then
    echo "Error: Failed to create BDA project"
    exit 1
fi

echo "Created BDA Project ARN: $BDA_PROJECT_ARN"

# Install dependencies
echo "Installing dependencies..."
npm install

# Deploy CDK stack
echo "Deploying CDK stack..."
npx cdk deploy --require-approval never --context bdaProjectArn="$BDA_PROJECT_ARN"

echo "Deployment completed!"
echo ""
echo "Next steps:"
echo "1. Go to AWS Console > Bedrock > Agent Core"
echo "2. Create new Agent Runtime using the Patent Orchestrator Docker image URI from the output"
echo "3. Use the Patent Orchestrator IAM Role ARN from the output"
echo "4. Configure environment variables for USPTO and Crossref gateways in Agent Core"
echo "5. Update the AGENT_RUNTIME_ARN in the CDK stack with the correct runtime ARN"
echo "6. Redeploy: npx cdk deploy"
