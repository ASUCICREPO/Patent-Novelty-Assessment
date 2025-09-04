#!/bin/bash
# Force ARM64 Docker build for Bedrock Agent Core compatibility

cd backend/PatentNoveltyAgent

# Build ARM64 image using buildx
docker buildx build --platform linux/arm64 --load -t patent-agent-arm64 .

# Tag for ECR
docker tag patent-agent-arm64:latest 216989103356.dkr.ecr.us-west-2.amazonaws.com/cdk-hnb659fds-container-assets-216989103356-us-west-2:arm64-manual

# Login to ECR
aws ecr get-login-password --region us-west-2 | docker login --username AWS --password-stdin 216989103356.dkr.ecr.us-west-2.amazonaws.com

# Push ARM64 image
docker push 216989103356.dkr.ecr.us-west-2.amazonaws.com/cdk-hnb659fds-container-assets-216989103356-us-west-2:arm64-manual

echo "ARM64 image pushed: 216989103356.dkr.ecr.us-west-2.amazonaws.com/cdk-hnb659fds-container-assets-216989103356-us-west-2:arm64-manual"
