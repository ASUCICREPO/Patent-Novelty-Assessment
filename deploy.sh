#!/bin/bash
# Complete End-to-End Deployment Pipeline

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
AWS_REGION="us-west-2"
AMPLIFY_APP_NAME="PatentNoveltyAssessment"
CODEBUILD_PROJECT_NAME="${PROJECT_NAME}-frontend"
REPOSITORY_URL="https://github.com/ASUCICREPO/patent-novelty-assessment.git" # IMPORTANT: GitHub repository URL

# Global variables to store IDs/URLs
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

# --- Phase 0: Create or Get BDA Project ---
print_status "📄 Phase 0: Setting up BDA Project..."

BDA_PROJECT_NAME="patent-novelty-bda"
print_status "Checking for existing BDA project: $BDA_PROJECT_NAME"

# Try to find existing project
EXISTING_PROJECT=$(AWS_PAGER="" aws bedrock-data-automation list-data-automation-projects \
    --region $AWS_REGION \
    --query "projects[?projectName=='$BDA_PROJECT_NAME'].projectArn" \
    --output text 2>/dev/null)

if [ -n "$EXISTING_PROJECT" ] && [ "$EXISTING_PROJECT" != "None" ]; then
    # Project exists - use existing ARN
    BDA_PROJECT_ARN=$EXISTING_PROJECT
    print_success "Found existing BDA project: $BDA_PROJECT_ARN"
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
    
    BDA_PROJECT_ARN=$(echo $BDA_RESPONSE | grep -o 'arn:aws:bedrock:[^"]*' | head -1)
    
    if [ -z "$BDA_PROJECT_ARN" ]; then
        print_error "Failed to extract BDA project ARN from response"
    fi
    
    print_success "Created BDA Project ARN: $BDA_PROJECT_ARN"
fi

# --- Phase 1: Backend Deployment (CDK) ---
print_status "🚀 Phase 1: Deploying CDK Infrastructure..."
cd backend || print_error "Failed to change to backend directory."

print_status "Installing CDK dependencies..."
npm install || print_error "Failed to install backend dependencies."

print_status "Deploying CDK stack (this may take a few minutes)..."
npx cdk deploy --require-approval never --context bdaProjectArn="$BDA_PROJECT_ARN" || print_error "CDK deployment failed."

print_status "Extracting API Gateway URL from CDK outputs..."
API_GATEWAY_URL=$(AWS_PAGER="" aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --query 'Stacks[0].Outputs[?OutputKey==`ApiGatewayUrl`].OutputValue' \
  --output text --region "$AWS_REGION")

if [ -z "$API_GATEWAY_URL" ] || [ "$API_GATEWAY_URL" = "None" ]; then
  print_error "Failed to extract API Gateway URL from CDK outputs. Please check CloudFormation stack: $STACK_NAME"
fi
print_success "API Gateway URL: $API_GATEWAY_URL"

cd .. # Go back to root directory

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
              "Sid": "AmplifyFullAccess",
              "Effect": "Allow",
              "Action": ["amplify:*"],
              "Resource": "*"
          },
          {
              "Sid": "S3FullAccess",
              "Effect": "Allow",
              "Action": ["s3:*"],
              "Resource": "*"
          },
          {
              "Sid": "IAMFullAccess",
              "Effect": "Allow",
              "Action": ["iam:*"],
              "Resource": "*"
          },
          {
              "Sid": "CloudFormationFullAccess",
              "Effect": "Allow",
              "Action": ["cloudformation:*"],
              "Resource": "*"
          },
          {
              "Sid": "CloudWatchLogsFullAccess",
              "Effect": "Allow",
              "Action": ["logs:*"],
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
    # Create Amplify app for static hosting (no repository connection needed)
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
    print_success "Amplify app created with ID: $AMPLIFY_APP_ID"
fi

# --- Phase 4: Create Amplify Branch ---
print_amplify "🌿 Phase 4: Creating Amplify Branch..."

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

# --- Phase 5: Create CodeBuild Project ---
print_codebuild "🏗️ Phase 5: Creating CodeBuild Project..."

# Build environment variables array for frontend
FRONTEND_ENV_VARS_ARRAY='{
    "name": "API_GATEWAY_URL",
    "value": "'"$API_GATEWAY_URL"'",
    "type": "PLAINTEXT"
  },{
    "name": "AMPLIFY_APP_ID",
    "value": "'"$AMPLIFY_APP_ID"'",
    "type": "PLAINTEXT"
  }'

FRONTEND_ENVIRONMENT='{
  "type": "LINUX_CONTAINER",
  "image": "aws/codebuild/amazonlinux-x86_64-standard:5.0",
  "computeType": "BUILD_GENERAL1_MEDIUM",
  "environmentVariables": ['"$FRONTEND_ENV_VARS_ARRAY"']
}'

FRONTEND_SOURCE='{
  "type":"GITHUB",
  "location":"'$REPOSITORY_URL'",
  "buildspec":"buildspec-frontend.yml"
}'

ARTIFACTS='{"type":"NO_ARTIFACTS"}'
SOURCE_VERSION="main"

print_status "Creating Frontend CodeBuild project '$CODEBUILD_PROJECT_NAME'..."
AWS_PAGER="" aws codebuild create-project \
  --name "$CODEBUILD_PROJECT_NAME" \
  --source "$FRONTEND_SOURCE" \
  --source-version "$SOURCE_VERSION" \
  --artifacts "$ARTIFACTS" \
  --environment "$FRONTEND_ENVIRONMENT" \
  --service-role "$ROLE_ARN" \
  --output json || print_error "Failed to create CodeBuild project."

print_success "CodeBuild project '$CODEBUILD_PROJECT_NAME' created."

# --- Phase 6: Start CodeBuild Job ---
print_codebuild "🚀 Phase 6: Starting CodeBuild Job for Frontend Build and Deploy..."

print_status "Starting frontend build for project '$CODEBUILD_PROJECT_NAME'..."
BUILD_ID=$(AWS_PAGER="" aws codebuild start-build \
  --project-name "$CODEBUILD_PROJECT_NAME" \
  --query 'build.id' \
  --output text)

if [ $? -ne 0 ]; then
  print_error "Failed to start the frontend build"
fi

print_success "Frontend build started successfully. Build ID: $BUILD_ID"

# Wait for frontend build to complete
print_status "Waiting for frontend build to complete..."
BUILD_STATUS="IN_PROGRESS"

while [ "$BUILD_STATUS" = "IN_PROGRESS" ]; do
  sleep 15
  BUILD_STATUS=$(AWS_PAGER="" aws codebuild batch-get-builds --ids "$BUILD_ID" --query 'builds[0].buildStatus' --output text)
  print_status "Frontend build status: $BUILD_STATUS"
done

if [ "$BUILD_STATUS" != "SUCCEEDED" ]; then
  print_error "Frontend build failed with status: $BUILD_STATUS"
  print_status "Check CodeBuild logs for details: https://console.aws.amazon.com/codesuite/codebuild/projects/$CODEBUILD_PROJECT_NAME/build/$BUILD_ID/"
  exit 1
fi

print_success "Frontend build and deployment completed successfully!"

# Get Amplify URL
print_status "Getting Amplify application URL..."
AMPLIFY_URL=$(AWS_PAGER="" aws amplify get-app \
    --app-id "$AMPLIFY_APP_ID" \
    --query 'app.defaultDomain' \
    --output text \
    --region "$AWS_REGION")

if [ -z "$AMPLIFY_URL" ] || [ "$AMPLIFY_URL" = "None" ]; then
    print_warning "Could not retrieve Amplify URL, using app ID instead"
    AMPLIFY_URL="$AMPLIFY_APP_ID.amplifyapp.com"
fi

print_success "Frontend deployed to Amplify successfully!"

# --- Final Summary ---
print_success "🎉 COMPLETE DEPLOYMENT SUCCESSFUL! 🎉"
echo ""
echo "📊 Deployment Summary:"
echo "   🌐 API Gateway URL: $API_GATEWAY_URL"
echo "   🚀 Amplify App ID: $AMPLIFY_APP_ID"
echo "   🌍 Frontend URL: https://main.$AMPLIFY_URL"
echo "   🏗️  CDK Stack: $STACK_NAME"
echo "   🌍 AWS Region: $AWS_REGION"
echo ""
echo "✅ What was deployed:"
echo "   ✓ CDK backend infrastructure"
echo "   ✓ API Gateway with Lambda functions"
echo "   ✓ S3 bucket for CodeBuild artifacts"
echo "   ✓ CodeBuild project for frontend"
echo "   ✓ Amplify application"
echo "   ✓ Frontend built and deployed to Amplify"
echo "   ✓ Environment variables configured"
echo ""
echo "🔗 Access your application:"
echo "   https://main.$AMPLIFY_URL"
echo ""
echo "📱 Next steps:"
echo "   1. Visit the application URL above"
echo "   2. Test file upload functionality"
echo "   3. Monitor in AWS Amplify Console and AWS CodeBuild Console"
echo "   4. Set up custom domain if needed"
