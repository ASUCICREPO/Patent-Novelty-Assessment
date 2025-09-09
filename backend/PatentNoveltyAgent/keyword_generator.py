#!/usr/bin/env python3
"""
Patent Keyword Generator Agent.
Reads BDA results and generates patent search keywords using pure AI.
"""

import json
import os
import boto3
import re
from datetime import datetime
from typing import Dict, Any
from strands import Agent, tool
from strands.models.bedrock import BedrockModel
from bedrock_agentcore.runtime import BedrockAgentCoreApp

# Environment Variables
AWS_REGION = os.getenv('AWS_REGION')
BUCKET_NAME = os.getenv('BUCKET_NAME')
DYNAMODB_TABLE = os.getenv('DYNAMODB_TABLE_NAME')

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

@tool
def store_keywords_in_dynamodb(pdf_filename: str, keywords_response: str) -> str:
    """
    Parse agent response and store keywords in DynamoDB.
    
    Args:
        pdf_filename: Name of the PDF file
        keywords_response: Full agent response with structured keywords
    
    Returns:
        Success or error message
    """
    try:
        # Initialize DynamoDB resource
        dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
        table = dynamodb.Table(DYNAMODB_TABLE)
        
        # Parse keywords from response for the 4 specific categories
        def extract_keywords(section_name: str, text: str) -> str:
            pattern = f"### {section_name}\\s*\\n([^#]*?)(?=\\n###|\\n##|$)"
            match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
            if match:
                lines = [line.strip('- ').strip() for line in match.group(1).split('\n') 
                        if line.strip() and line.strip().startswith('-')]
                return ', '.join(lines)
            return ""
        
        # Create timestamp
        timestamp = datetime.utcnow().isoformat()
        
        # Store in DynamoDB with only the 4 required categories
        item = {
            'pdf_filename': pdf_filename,
            'timestamp': timestamp,
            'application_use': extract_keywords("Application/Use", keywords_response),
            'mechanism_composition': extract_keywords("Mechanism/Composition", keywords_response),
            'synonyms': extract_keywords("Synonyms", keywords_response),
            'patent_classifications': extract_keywords("Patent Classifications", keywords_response),
            'processing_status': 'completed'
        }
        
        # Put item in DynamoDB
        table.put_item(Item=item)
        
        return f"Successfully stored keywords for {pdf_filename} in DynamoDB table {DYNAMODB_TABLE}"
        
    except Exception as e:
        error_msg = f"Error storing keywords in DynamoDB: {str(e)}"
        print(error_msg)  # Log for debugging
        return error_msg

# Create the keyword generator agent
keyword_generator = Agent(
    model="us.anthropic.claude-3-7-sonnet-20250219-v1:0",
    tools=[read_bda_results, store_keywords_in_dynamodb],
    system_prompt="""You are a Patent Keyword Generator Agent specialized in analyzing invention disclosure documents.

Your task is to:
1. Read the BDA processed document using the read_bda_results tool
2. Analyze the invention content using pure AI reasoning
3. Generate comprehensive patent search keywords across 4 categories (aim for 15-20 total keywords)
4. Store the results in DynamoDB using the store_keywords_in_dynamodb tool

Analyze the document and intelligently distribute keywords across these 4 categories based on what you identify:

## Patent Search Keywords

### Application/Use
- [List keywords for applications, uses, medical conditions, therapeutic areas, target problems - as many as relevant]

### Mechanism/Composition
- [List keywords for technical mechanisms, compositions, materials, compounds, processes - as many as relevant]

### Synonyms
- [List alternative terms, related terminology, similar expressions - as many as useful for search]

### Patent Classifications
- [List relevant patent classification codes if identifiable from content]

Use your judgment to determine how many keywords belong in each category based on the invention's nature. Some inventions may have more application keywords, others more mechanism keywords. Aim for 15-20 total keywords across all categories. After generating the keywords, ALWAYS use the store_keywords_in_dynamodb tool to save the results."""
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
    
    # Extract PDF filename from BDA file path
    pdf_filename = "unknown"
    if bda_file_path:
        # Path format: temp/docParser/filename-timestamp/job-id/0/standard_output/0/result.json
        path_parts = bda_file_path.split('/')
        if len(path_parts) > 2:
            filename_timestamp = path_parts[2]  # e.g., "ROI2022-test-2025-08-31T00-33-09-644Z"
            # Extract just the filename part before the timestamp
            pdf_filename = filename_timestamp.split('-2025-')[0] if '-2025-' in filename_timestamp else filename_timestamp
    
    # Add BDA file path and PDF filename to prompt
    enhanced_prompt = prompt
    if bda_file_path:
        enhanced_prompt += f"\n\nFirst, use the read_bda_results tool to read the document content from: {bda_file_path}"
        enhanced_prompt += f"\n\nAfter generating the keywords, use the store_keywords_in_dynamodb tool with:"
        enhanced_prompt += f"\n- pdf_filename: '{pdf_filename}'"
        enhanced_prompt += f"\n- keywords_response: [your complete keyword generation response]"
    
    try:
        # Collect the complete response from streaming events
        full_response = ""
        async for event in keyword_generator.stream_async(enhanced_prompt):
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
