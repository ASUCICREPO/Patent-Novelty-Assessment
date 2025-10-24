#!/bin/bash
# Complete End-to-End Deployment Pipeline
# Based on PDF_accessability_UI working approach: CodeBuild + Amplify integration

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m' # No Color

# Configuration
STACK_NAME="PatentNoveltyStack"
BDA_PROJECT_ARN="arn:aws:bedrock:us-west-2:216989103356:data-automation-project/97146aaabae2"
AWS_REGION="us-west-2"
AMPLIFY_APP_NAME="PatentNoveltyAssessment"
AMPLIFY_BRANCH_NAME="main"
CODEBUILD_PROJECT_NAME="patent-novelty-frontend"

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

print_amplify() {
    echo -e "${PURPLE}[AMPLIFY]${NC} $1"
}

# --- Phase 1: Backend Deployment (CDK) ---
print_status "🚀 Phase 1: Deploying CDK Infrastructure..."
cd backend || print_error "Failed to change to backend directory."

print_status "Installing CDK dependencies..."
npm install || print_error "Failed to install backend dependencies."

print_status "Deploying CDK stack (this may take a few minutes)..."
npx cdk deploy --require-approval never --context bdaProjectArn="$BDA_PROJECT_ARN" || print_error "CDK deployment failed."

print_status "Extracting API Gateway URL from CDK outputs..."
API_GATEWAY_URL=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --query 'Stacks[0].Outputs[?OutputKey==`ApiGatewayUrl`].OutputValue' \
  --output text --region "$AWS_REGION" --no-cli-pager)

if [ -z "$API_GATEWAY_URL" ] || [ "$API_GATEWAY_URL" = "None" ]; then
  print_error "Failed to extract API Gateway URL from CDK outputs. Please check CloudFormation stack: $STACK_NAME"
fi
print_success "API Gateway URL: $API_GATEWAY_URL"

cd .. # Go back to root directory

# --- Phase 2: Create CodeBuild Project ---
print_status "🔨 Phase 2: Setting up CodeBuild Project..."

# Check if CodeBuild project exists
EXISTING_PROJECT=$(aws codebuild list-projects --query "projects[?contains(@, '$CODEBUILD_PROJECT_NAME')]" --output text --no-cli-pager)

if [ -n "$EXISTING_PROJECT" ]; then
    print_warning "CodeBuild project '$CODEBUILD_PROJECT_NAME' already exists"
else
    print_status "Creating CodeBuild project for frontend deployment..."
    
    # Create CodeBuild project
    aws codebuild create-project \
        --name "$CODEBUILD_PROJECT_NAME" \
        --description "Frontend build and deployment for Patent Novelty Assessment" \
        --source type=GITHUB,location=https://github.com/dummy/repo.git \
        --artifacts type=NO_ARTIFACTS \
        --environment type=LINUX_CONTAINER,image=aws/codebuild/standard:7.0 \
        --service-role arn:aws:iam::$(aws sts get-caller-identity --query Account --output text):role/CodeBuildServiceRole \
        --buildspec buildspec-frontend.yml \
        --no-cli-pager || print_warning "Failed to create CodeBuild project. You may need to create it manually."
    
    print_success "CodeBuild project created: $CODEBUILD_PROJECT_NAME"
fi

# --- Phase 3: Create Amplify App ---
print_amplify "Phase 3: Creating Amplify Application..."

# Check if app already exists
EXISTING_APP=$(aws amplify list-apps --query "apps[?name=='$AMPLIFY_APP_NAME'].appId" --output text --no-cli-pager)

if [ -n "$EXISTING_APP" ] && [ "$EXISTING_APP" != "None" ]; then
    print_warning "Amplify app '$AMPLIFY_APP_NAME' already exists with ID: $EXISTING_APP"
    AMPLIFY_APP_ID=$EXISTING_APP
else
    # Create Amplify app
    print_status "Creating Amplify app: $AMPLIFY_APP_NAME"
    
    AMPLIFY_APP_ID=$(aws amplify create-app \
        --name "$AMPLIFY_APP_NAME" \
        --description "Patent Novelty Assessment Application" \
        --platform WEB_COMPUTE \
        --environment-variables NEXT_PUBLIC_API_BASE_URL="$API_GATEWAY_URL" \
        --query 'app.appId' \
        --output text \
        --no-cli-pager)
    
    if [ -z "$AMPLIFY_APP_ID" ] || [ "$AMPLIFY_APP_ID" = "None" ]; then
        print_error "Failed to create Amplify app"
        exit 1
    fi
    
    print_success "Amplify app created with ID: $AMPLIFY_APP_ID"
fi

# --- Phase 4: Create Amplify Branch ---
print_amplify "Phase 4: Creating Amplify Branch..."

# Check if main branch exists
EXISTING_BRANCH=$(aws amplify get-branch \
    --app-id $AMPLIFY_APP_ID \
    --branch-name main \
    --query 'branch.branchName' \
    --output text \
    --no-cli-pager 2>/dev/null || echo "None")

if [ "$EXISTING_BRANCH" = "main" ]; then
    print_warning "Main branch already exists"
else
    # Create main branch
    print_status "Creating main branch..."
    
    aws amplify create-branch \
        --app-id $AMPLIFY_APP_ID \
        --branch-name main \
        --description "Main production branch" \
        --stage PRODUCTION \
        --no-cli-pager
    
    print_success "Main branch created"
fi

# --- Phase 5: Deploy Frontend using CodeBuild ---
print_status "🚀 Phase 5: Deploying Frontend using CodeBuild..."

# Start CodeBuild job
print_status "Starting CodeBuild job for frontend deployment..."
BUILD_ID=$(aws codebuild start-build \
    --project-name "$CODEBUILD_PROJECT_NAME" \
    --environment-variables-override \
        name=API_GATEWAY_URL,value="$API_GATEWAY_URL" \
    --query 'build.id' \
    --output text \
    --no-cli-pager)

if [ -z "$BUILD_ID" ] || [ "$BUILD_ID" = "None" ]; then
    print_error "Failed to start CodeBuild job"
    exit 1
fi

print_success "CodeBuild job started with ID: $BUILD_ID"

# Wait for build to complete
print_status "Waiting for CodeBuild to complete (this may take 5-10 minutes)..."

while true; do
    STATUS=$(aws codebuild batch-get-builds \
        --ids "$BUILD_ID" \
        --query 'builds[0].buildStatus' \
        --output text \
        --no-cli-pager)
    
    case $STATUS in
        "SUCCEEDED")
            print_success "CodeBuild completed successfully!"
            break
            ;;
        "FAILED"|"STOPPED"|"TIMED_OUT")
            print_error "CodeBuild failed with status: $STATUS"
            exit 1
            ;;
        "IN_PROGRESS")
            print_status "CodeBuild in progress... (Status: $STATUS)"
            sleep 30
            ;;
        *)
            print_warning "Unknown status: $STATUS"
            sleep 30
            ;;
    esac
done

# --- Phase 6: Deploy to Amplify ---
print_amplify "Phase 6: Deploying to Amplify..."

# Start Amplify deployment
print_status "Starting Amplify deployment..."
DEPLOYMENT_ID=$(aws amplify start-deployment \
    --app-id $AMPLIFY_APP_ID \
    --branch-name main \
    --source-url "s3://$(aws codebuild batch-get-builds --ids $BUILD_ID --query 'builds[0].artifacts.location' --output text --no-cli-pager)" \
    --query 'jobSummary.jobId' \
    --output text \
    --no-cli-pager)

if [ -z "$DEPLOYMENT_ID" ] || [ "$DEPLOYMENT_ID" = "None" ]; then
    print_error "Failed to start Amplify deployment"
    exit 1
fi

print_success "Amplify deployment started with ID: $DEPLOYMENT_ID"

# Wait for Amplify deployment to complete
print_status "Waiting for Amplify deployment to complete (this may take 5-10 minutes)..."

while true; do
    STATUS=$(aws amplify get-job \
        --app-id $AMPLIFY_APP_ID \
        --branch-name main \
        --job-id $DEPLOYMENT_ID \
        --query 'job.summary.status' \
        --output text \
        --no-cli-pager)
    
    case $STATUS in
        "SUCCEED")
            print_success "Amplify deployment completed successfully!"
            break
            ;;
        "FAILED"|"CANCELLED")
            print_error "Amplify deployment failed with status: $STATUS"
            exit 1
            ;;
        "PENDING"|"RUNNING"|"IN_PROGRESS")
            print_status "Amplify deployment in progress... (Status: $STATUS)"
            sleep 30
            ;;
        *)
            print_warning "Unknown status: $STATUS"
            sleep 30
            ;;
    esac
done

# --- Phase 7: Get Amplify URL ---
print_amplify "Phase 7: Getting Amplify Application URL..."

# Get the app details
APP_DOMAIN=$(aws amplify get-app \
    --app-id $AMPLIFY_APP_ID \
    --query 'app.defaultDomain' \
    --output text \
    --no-cli-pager)

if [ -n "$APP_DOMAIN" ] && [ "$APP_DOMAIN" != "None" ]; then
    AMPLIFY_URL="https://main.$APP_DOMAIN"
    print_success "Amplify Application URL: $AMPLIFY_URL"
else
    print_warning "Could not retrieve Amplify URL. Check the Amplify console."
fi

# --- Final Summary ---
print_success "🎉 COMPLETE DEPLOYMENT SUCCESSFUL!"
echo ""
echo "📊 Deployment Summary:"
echo "   🌐 API Gateway URL: $API_GATEWAY_URL"
echo "   🚀 Amplify App ID: $AMPLIFY_APP_ID"
echo "   🌍 Amplify URL: $AMPLIFY_URL"
echo "   🏗️  CDK Stack: $STACK_NAME"
echo "   🌍 AWS Region: $AWS_REGION"
echo ""
echo "✅ What was deployed:"
echo "   ✓ CDK backend infrastructure"
echo "   ✓ API Gateway with Lambda functions"
echo "   ✓ CodeBuild project for frontend"
echo "   ✓ Amplify application"
echo "   ✓ Frontend deployed via CodeBuild + Amplify"
echo "   ✓ Environment variables configured"
echo ""
echo "🔗 Access your application:"
echo "   $AMPLIFY_URL"
echo ""
echo "📱 Next steps:"
echo "   1. Visit the application URL above"
echo "   2. Test file upload functionality"
echo "   3. Monitor in AWS Amplify Console"
echo "   4. Set up custom domain if needed"
