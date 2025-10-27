#!/bin/bash
# Complete End-to-End Deployment Pipeline
# Uses single unified CodeBuild project for backend and frontend

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m' # No Color

# Configuration
TIMESTAMP=$(date +%Y%m%d%H%M%S)
PROJECT_NAME="patent-novelty-${TIMESTAMP}"
STACK_NAME="PatentNoveltyStack"
AWS_REGION=$(aws configure get region || echo "us-west-2")
AMPLIFY_APP_NAME="PatentNoveltyAssessment"
CODEBUILD_PROJECT_NAME="${PROJECT_NAME}-deployment"
REPOSITORY_URL="https://github.com/ASUCICREPO/patent-novelty-assessment.git" # IMPORTANT: repo url from which codebuild runs

# Global variables
API_GATEWAY_URL=""
AMPLIFY_APP_ID=""
AMPLIFY_URL=""
ROLE_ARN=""

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
    exit 1
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_codebuild() {
    echo -e "${PURPLE}[CODEBUILD]${NC} $1"
}

print_amplify() {
    echo -e "${PURPLE}[AMPLIFY]${NC} $1"
}

# --- Phase 0: Prompt for Agent Runtime ARN ---
print_status "🤖 Phase 0: Agent Runtime ARN Configuration..."

echo ""
echo "Before proceeding, you must manually create an Agent Core Runtime in the AWS Console."
echo "Instructions:"
echo "  1. Go to AWS Bedrock Console > Agent Core"
echo "  2. Create a new Agent Runtime"
echo "  3. Copy the Runtime ARN (format: arn:aws:bedrock-agentcore:REGION:ACCOUNT:runtime/RUNTIME-ID)"
echo ""
read -p "Enter your Agent Runtime ARN: " AGENT_RUNTIME_ARN

if [ -z "$AGENT_RUNTIME_ARN" ]; then
    print_error "Agent Runtime ARN is required. Please create an Agent Core Runtime first."
fi

# Validate ARN format
if [[ ! "$AGENT_RUNTIME_ARN" =~ ^arn:aws:bedrock-agentcore:[a-z0-9-]+:[0-9]+:runtime/.+ ]]; then
    print_error "Invalid Agent Runtime ARN format. Expected: arn:aws:bedrock-agentcore:REGION:ACCOUNT:runtime/RUNTIME-ID"
fi

print_success "Agent Runtime ARN: REDACTED"

# --- Phase 1: Create or Get BDA Project ---
print_status "📄 Phase 1: Setting up BDA Project..."

BDA_PROJECT_NAME="patent-novelty-bda"
print_status "Checking for existing BDA project: $BDA_PROJECT_NAME"

# Try to find existing project
EXISTING_PROJECT=$(AWS_PAGER="" aws bedrock-data-automation list-data-automation-projects \
    --region "$AWS_REGION" \
    --query "projects[?projectName=='$BDA_PROJECT_NAME'].projectArn" \
    --output text 2>/dev/null)

if [ -n "$EXISTING_PROJECT" ] && [ "$EXISTING_PROJECT" != "None" ]; then
    # Project exists - use existing ARN
    BDA_PROJECT_ARN=$EXISTING_PROJECT
    print_success "Found existing BDA project: REDACTED"
else
    # Project doesn't exist - create new one
    print_status "Creating new BDA project: $BDA_PROJECT_NAME"
    
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
        --region $AWS_REGION 2>&1)
    
    if [ $? -ne 0 ]; then
        print_error "Failed to create BDA project: $BDA_RESPONSE"
    fi
    
    BDA_PROJECT_ARN=$(echo $BDA_RESPONSE | grep -o 'arn:aws:bedrock-data-automation:[^"]*' | head -1)
    
    if [ -z "$BDA_PROJECT_ARN" ]; then
        print_error "Failed to extract BDA project ARN from response"
    fi
    
    print_success "Created BDA Project ARN: REDACTED"
fi

# --- Phase 2: Create IAM Service Role ---
print_status "🔐 Phase 2: Creating IAM Service Role..."

ROLE_NAME="${PROJECT_NAME}-service-role"
print_status "Checking for IAM role: $ROLE_NAME"

if aws iam get-role --role-name "$ROLE_NAME" >/dev/null 2>&1; then
    print_success "IAM role exists"
    ROLE_ARN=$(aws iam get-role --role-name "$ROLE_NAME" --query 'Role.Arn' --output text)
else
    print_status "Creating IAM role: $ROLE_NAME"
    TRUST_DOC='{
      "Version":"2012-10-17",
      "Statement":[{
        "Effect":"Allow",
        "Principal":{"Service":"codebuild.amazonaws.com"},
        "Action":"sts:AssumeRole"
      }]
    }'

    ROLE_ARN=$(aws iam create-role \
      --role-name "$ROLE_NAME" \
      --assume-role-policy-document "$TRUST_DOC" \
      --query 'Role.Arn' --output text)

    print_status "Attaching custom deployment policy..."
    CUSTOM_POLICY='{
      "Version": "2012-10-17",
      "Statement": [
          {
              "Sid": "FullDeploymentAccess",
              "Effect": "Allow",
              "Action": [
                  "cloudformation:*",
                  "iam:*",
                  "lambda:*",
                  "dynamodb:*",
                  "s3:*",
                  "bedrock:*",
                  "bedrock-agentcore:*",
                  "amplify:*",
                  "codebuild:*",
                  "logs:*",
                  "apigateway:*",
                  "ecr:*",
                  "ssm:*",
                  "events:*"
              ],
              "Resource": "*"
          },
          {
              "Sid": "STSAccess",
              "Effect": "Allow",
              "Action": ["sts:GetCallerIdentity", "sts:AssumeRole"],
              "Resource": "*"
          }
      ]
    }'

    aws iam put-role-policy \
      --role-name "$ROLE_NAME" \
      --policy-name "DeploymentPolicy" \
      --policy-document "$CUSTOM_POLICY"

    print_success "IAM role created"
    print_status "Waiting for IAM role to propagate for 10 seconds..."
    sleep 10
fi

# --- Phase 3: Create Amplify App (Static Hosting) ---
print_amplify "🌐 Phase 3: Creating Amplify Application for Static Hosting..."

# Check if app already exists
EXISTING_APP_ID=$(AWS_PAGER="" aws amplify list-apps --query "apps[?name=='$AMPLIFY_APP_NAME'].appId" --output text --region "$AWS_REGION")

if [ -n "$EXISTING_APP_ID" ] && [ "$EXISTING_APP_ID" != "None" ]; then
    print_warning "Amplify app '$AMPLIFY_APP_NAME' already exists with ID: $EXISTING_APP_ID"
    AMPLIFY_APP_ID=$EXISTING_APP_ID
else
    # Create Amplify app for static hosting
    print_status "Creating Amplify app for static hosting: $AMPLIFY_APP_NAME"

    AMPLIFY_APP_ID=$(AWS_PAGER="" aws amplify create-app \
        --name "$AMPLIFY_APP_NAME" \
        --description "Patent Novelty Assessment Application" \
        --platform WEB_COMPUTE \
        --query 'app.appId' \
        --output text \
        --region "$AWS_REGION")

    if [ -z "$AMPLIFY_APP_ID" ] || [ "$AMPLIFY_APP_ID" = "None" ]; then
        print_error "Failed to create Amplify app"
        exit 1
    fi
    print_success "Amplify app created with ID: REDACTED"
fi

# Check if main branch exists
EXISTING_BRANCH=$(AWS_PAGER="" aws amplify get-branch \
    --app-id "$AMPLIFY_APP_ID" \
    --branch-name main \
    --query 'branch.branchName' \
    --output text \
    --region "$AWS_REGION" 2>/dev/null || echo "None")

if [ "$EXISTING_BRANCH" = "main" ]; then
    print_warning "main branch already exists"
else
    # Create main branch
    print_status "Creating main branch..."

    AWS_PAGER="" aws amplify create-branch \
        --app-id "$AMPLIFY_APP_ID" \
        --branch-name main \
        --description "Main production branch" \
        --stage PRODUCTION \
        --region "$AWS_REGION" || print_error "Failed to create Amplify branch."
    print_success "main branch created"
fi

# --- Phase 4: Create Unified CodeBuild Project ---
print_codebuild "🏗️ Phase 4: Creating Unified CodeBuild Project..."

# Build environment variables for unified deployment
ENV_VARS_ARRAY='{
    "name": "BDA_PROJECT_ARN",
    "value": "'"$BDA_PROJECT_ARN"'",
    "type": "PLAINTEXT"
  },{
    "name": "AGENT_RUNTIME_ARN",
    "value": "'"$AGENT_RUNTIME_ARN"'",
    "type": "PLAINTEXT"
  },{
    "name": "AMPLIFY_APP_ID",
    "value": "'"$AMPLIFY_APP_ID"'",
    "type": "PLAINTEXT"
  }'

ENVIRONMENT=$(cat <<EOF
{
  "type": "ARM_CONTAINER",
  "image": "aws/codebuild/amazonlinux-aarch64-standard:3.0",
  "computeType": "BUILD_GENERAL1_LARGE",
  "privilegedMode": true,
  "environmentVariables": [$ENV_VARS_ARRAY]
}
EOF
)

SOURCE='{
  "type":"GITHUB",
  "location":"'$REPOSITORY_URL'",
  "buildspec":"buildspec.yml"
}'

ARTIFACTS='{"type":"NO_ARTIFACTS"}'
SOURCE_VERSION="main"

print_status "Creating unified CodeBuild project '$CODEBUILD_PROJECT_NAME'..."
AWS_PAGER="" aws codebuild create-project \
  --name "$CODEBUILD_PROJECT_NAME" \
  --source "$SOURCE" \
  --source-version "$SOURCE_VERSION" \
  --artifacts "$ARTIFACTS" \
  --environment "$ENVIRONMENT" \
  --service-role "$ROLE_ARN" \
  --output json > /dev/null || print_error "Failed to create CodeBuild project."

print_success "Unified CodeBuild project '$CODEBUILD_PROJECT_NAME' created."

# --- Phase 5: Start Unified Build ---
print_codebuild "🚀 Phase 5: Starting Unified Deployment (Backend + Frontend)..."

print_status "Starting deployment build for project '$CODEBUILD_PROJECT_NAME'..."
BUILD_ID=$(AWS_PAGER="" aws codebuild start-build \
  --project-name "$CODEBUILD_PROJECT_NAME" \
  --query 'build.id' \
  --output text)

if [ $? -ne 0 ]; then
  print_error "Failed to start the deployment build"
fi

print_success "Deployment build started successfully. Build ID: $BUILD_ID"

# Stream logs
print_status "Streaming deployment logs..."
print_status "Build ID: $BUILD_ID"
echo ""

# Extract log group and stream from build ID
LOG_GROUP="/aws/codebuild/$CODEBUILD_PROJECT_NAME"
LOG_STREAM=$(echo "$BUILD_ID" | cut -d':' -f2)

# Wait a few seconds for logs to start
sleep 5

# Stream logs with filtering for CDK outputs only
BUILD_STATUS="IN_PROGRESS"
LAST_TOKEN=""
IN_CDK_OUTPUT_SECTION=false

print_status "Monitoring build progress (showing CDK outputs only)..."
echo ""

while [ "$BUILD_STATUS" = "IN_PROGRESS" ]; do
  # Get logs
  if [ -z "$LAST_TOKEN" ]; then
    LOG_OUTPUT=$(AWS_PAGER="" aws logs get-log-events \
      --log-group-name "$LOG_GROUP" \
      --log-stream-name "$LOG_STREAM" \
      --start-from-head \
      --output json 2>/dev/null)
  else
    LOG_OUTPUT=$(AWS_PAGER="" aws logs get-log-events \
      --log-group-name "$LOG_GROUP" \
      --log-stream-name "$LOG_STREAM" \
      --next-token "$LAST_TOKEN" \
      --output json 2>/dev/null)
  fi
  
  # Filter logs to show only CDK outputs and important milestones
  if [ -n "$LOG_OUTPUT" ]; then
    echo "$LOG_OUTPUT" | jq -r '.events[]?.message' 2>/dev/null | while IFS= read -r line; do
      # Skip container metadata and empty lines
      if [[ "$line" =~ ^\[Container\] ]] || [[ -z "$line" ]]; then
        continue
      fi
      
      # Show phase transitions
      if [[ "$line" =~ "BACKEND DEPLOYMENT" ]] || \
         [[ "$line" =~ "FRONTEND DEPLOYMENT" ]] || \
         [[ "$line" =~ "Deploying CDK stack" ]] || \
         [[ "$line" =~ "Building Next.js" ]] || \
         [[ "$line" =~ "Deploying frontend to Amplify" ]]; then
        echo -e "${BLUE}[PHASE]${NC} $line"
        continue
      fi
      
      # Detect CDK output section start
      if [[ "$line" =~ "Outputs:" ]] || [[ "$line" =~ "Stack ARN:" ]]; then
        IN_CDK_OUTPUT_SECTION=true
        echo -e "${GREEN}[CDK OUTPUT]${NC} $line"
        continue
      fi
      
      # Show CDK outputs
      if [[ "$IN_CDK_OUTPUT_SECTION" == true ]]; then
        # Stop showing when we hit the next phase
        if [[ "$line" =~ "Stack ARN:" ]] || \
           [[ "$line" =~ "CDK deployment complete" ]] || \
           [[ "$line" =~ "Extracting API Gateway URL" ]]; then
          echo -e "${GREEN}[CDK OUTPUT]${NC} $line"
          IN_CDK_OUTPUT_SECTION=false
          continue
        fi
        
        # Show output lines (they typically start with "PatentNoveltyStack.")
        if [[ "$line" =~ ^PatentNoveltyStack\. ]] || [[ "$line" =~ ^[[:space:]]*PatentNoveltyStack\. ]]; then
          echo -e "${GREEN}[CDK OUTPUT]${NC} $line"
        fi
      fi
      
      # Show errors
      if [[ "$line" =~ "ERROR" ]] || [[ "$line" =~ "Error" ]] || [[ "$line" =~ "Failed" ]]; then
        echo -e "${RED}[ERROR]${NC} $line"
      fi
      
      # Show success messages
      if [[ "$line" =~ "successfully" ]] || [[ "$line" =~ "Complete deployment finished" ]]; then
        echo -e "${GREEN}[SUCCESS]${NC} $line"
      fi
    done
    
    LAST_TOKEN=$(echo "$LOG_OUTPUT" | jq -r '.nextForwardToken' 2>/dev/null)
  fi
  
  # Check build status
  BUILD_STATUS=$(AWS_PAGER="" aws codebuild batch-get-builds --ids "$BUILD_ID" --query 'builds[0].buildStatus' --output text)
  
  sleep 3
done

echo ""
print_status "Deployment build status: $BUILD_STATUS"

if [ "$BUILD_STATUS" != "SUCCEEDED" ]; then
  print_error "Deployment build failed with status: $BUILD_STATUS"
  print_status "Check CodeBuild logs for details: https://console.aws.amazon.com/codesuite/codebuild/projects/$CODEBUILD_PROJECT_NAME/build/$BUILD_ID/"
  exit 1
fi

print_success "Complete deployment finished successfully!"

# Extract API Gateway URL from CloudFormation
print_status "Extracting deployment information..."
API_GATEWAY_URL=$(AWS_PAGER="" aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --query "Stacks[0].Outputs[?OutputKey==\`ApiGatewayUrl\`].OutputValue" \
  --output text --region "$AWS_REGION")

if [ -z "$API_GATEWAY_URL" ] || [ "$API_GATEWAY_URL" = "None" ]; then
  print_warning "Could not extract API Gateway URL from CDK outputs"
  API_GATEWAY_URL="Check CloudFormation console"
fi

# Get Amplify URL
AMPLIFY_URL=$(AWS_PAGER="" aws amplify get-app \
    --app-id "$AMPLIFY_APP_ID" \
    --query 'app.defaultDomain' \
    --output text \
    --region "$AWS_REGION")

if [ -z "$AMPLIFY_URL" ] || [ "$AMPLIFY_URL" = "None" ]; then
    AMPLIFY_URL="$AMPLIFY_APP_ID.amplifyapp.com"
fi

# --- Final Summary ---
print_success "COMPLETE DEPLOYMENT SUCCESSFUL!"
echo ""
echo "Deployment Summary:"
echo "   API Gateway URL: REDACTED"
echo "   Amplify App ID: REDACTED"
echo "   Frontend URL: https://main.$AMPLIFY_URL"
echo "   CDK Stack: $STACK_NAME"
echo "   AWS Region: $AWS_REGION"
echo ""
echo "What was deployed:"
echo "   - BDA Project for document processing"
echo "   - CDK backend infrastructure via CodeBuild"
echo "   - API Gateway with Lambda functions"
echo "   - DynamoDB tables"
echo "   - S3 bucket with restricted CORS policy"
echo "   - Docker image for Agent Core Runtime"
echo "   - Frontend built and deployed to Amplify via CodeBuild"
echo ""
echo "Access your application:"
echo "   https://main.$AMPLIFY_URL"
echo ""
echo "Next steps:"
echo "   1. Visit the application URL above"
echo "   2. Test file upload functionality"
echo "   3. Monitor in AWS Amplify Console and AWS CodeBuild Console"
echo "   4. Set up custom domain if needed"
