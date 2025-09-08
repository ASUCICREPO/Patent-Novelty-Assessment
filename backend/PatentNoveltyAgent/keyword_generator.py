#!/usr/bin/env python3
"""
Patent Keyword Generator Agent.
Reads BDA results and generates patent search keywords using pure AI.
"""

import json
import os
import boto3
from typing import Dict, Any
from strands import Agent, tool
from strands.models.bedrock import BedrockModel
from bedrock_agentcore.runtime import BedrockAgentCoreApp

# Environment Variables
AWS_REGION = os.getenv('AWS_REGION')
BUCKET_NAME = os.getenv('BUCKET_NAME')

@tool
def read_bda_results(file_path: str) -> str:
    """
    Read BDA processing results from S3 and return the full document content.
    
    Args:
        file_path: S3 path to the BDA result.json file
    
    Returns:
        Full document text content from BDA processing
    """
    try:
        s3_client = boto3.client('s3', region_name=AWS_REGION)
        response = s3_client.get_object(Bucket=BUCKET_NAME, Key=file_path)
        content = response['Body'].read().decode('utf-8')
        bda_data = json.loads(content)
        
        # Extract the full document text
        document_text = bda_data.get('document', {}).get('representation', {}).get('text', '')
        
        if not document_text:
            return "Error: No document text found in BDA results"
        
        return document_text
    except Exception as e:
        return f"Error reading BDA results: {str(e)}"

# Create the keyword generator agent
keyword_generator = Agent(
    model="us.anthropic.claude-3-7-sonnet-20250219-v1:0",
    tools=[read_bda_results],
    system_prompt="""You are a Patent Keyword Generator Agent specialized in analyzing invention disclosure documents.

Your task is to:
1. Read the BDA processed document using the read_bda_results tool
2. Analyze the invention content using pure AI reasoning
3. Generate comprehensive patent search keywords

When analyzing the document, extract:
- Core technical terms (5-8 most important)
- Novel concepts unique to this invention
- Functional keywords (what the invention does)
- Structural keywords (how it's built/designed)
- Application domain keywords
- Broad search terms for comprehensive coverage
- Specific search terms for precise matching

Present your analysis in this format:

## Invention Summary
[Brief 2-3 sentence summary of the invention]

## Patent Search Keywords

### Core Technical Terms
- [List 5-8 most important technical terms]

### Novel Concepts
- [List 3-5 unique concepts specific to this invention]

### Functional Keywords
- [List what the invention does/accomplishes]

### Structural Keywords
- [List how it's built/designed/implemented]

### Domain Keywords
- [List application areas/industries]

### Search Strategy
**Broad Search Terms:** [For comprehensive prior art search]
**Specific Search Terms:** [For precise novelty assessment]

Always provide clear, actionable keywords that patent researchers can use effectively."""
)

async def handle_agent_request(payload):
    """Handle agent request for patent keyword generation."""
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            payload = {"prompt": payload}
    
    prompt = payload.get("prompt")
    bda_file_path = payload.get("bda_file_path")
    
    if not prompt:
        yield {"error": "Error: 'prompt' is required."}
        return
    
    # Add BDA file path to prompt if provided
    if bda_file_path:
        prompt += f"\n\nFirst, use the read_bda_results tool to read the document content from: {bda_file_path}"
    
    try:
        # Collect the complete response from streaming events
        full_response = ""
        async for event in keyword_generator.stream_async(prompt):
            if "data" in event:
                full_response += event["data"]
            elif "current_tool_use" in event and event["current_tool_use"].get("name"):
                yield {"tool_name": event["current_tool_use"]["name"]}
            elif "error" in event:
                yield {"error": event["error"]}
                return
        
        # Yield the complete response once streaming is done
        if full_response.strip():
            yield {"response": full_response}
        else:
            yield {"error": "No response generated from agent"}
                
    except Exception as e:
        yield {"error": f"Error processing request: {str(e)}"}

app = BedrockAgentCoreApp()

@app.entrypoint
async def invoke(payload: Dict[str, Any]):
    """AgentCore streaming entrypoint."""
    async for event in handle_agent_request(payload):
        yield event

if __name__ == "__main__":
    app.run()
