# Explicitly force ARM64 platform
FROM --platform=linux/arm64 public.ecr.aws/docker/library/python:3.12-slim
WORKDIR /app

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

# Force rebuild trigger
RUN echo "ARM64 build $(date)" > /tmp/build_info

CMD ["opentelemetry-instrument", "python", "patent_novelty_agent.py"]
