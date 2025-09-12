# Use ARM64 base image without platform flag to avoid multi-arch manifest
FROM public.ecr.aws/docker/library/python:3.12-slim
WORKDIR /app

# Force rebuild - Updated for Patent Novelty Orchestrator
COPY requirements.txt requirements.txt
# Install from requirements file
RUN pip install -r requirements.txt

RUN pip install aws-opentelemetry-distro>=0.10.1

# Signal that this is running in Docker for host binding logic
ENV DOCKER_CONTAINER=1

# All AWS environment variables (AWS_REGION, BUCKET_NAME, etc.) 
# will be provided by AgentCore at runtime

# Create non-root user
RUN useradd -m -u 1000 bedrock_agentcore
USER bedrock_agentcore

EXPOSE 8080
EXPOSE 8000

# Copy entire project (respecting .dockerignore)
COPY . .

CMD ["opentelemetry-instrument", "python", "orchestrator.py"]