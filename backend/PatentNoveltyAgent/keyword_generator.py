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
    Parse agent response and store patent analysis data in DynamoDB.
    
    Args:
        pdf_filename: Name of the PDF file
        keywords_response: Full agent response with structured patent analysis
    
    Returns:
        Success or error message
    """
    try:
        # Initialize DynamoDB resource
        dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
        table = dynamodb.Table(DYNAMODB_TABLE)
        
        # Parse the structured response
        def extract_section(section_name: str, text: str) -> str:
            # Look for ## Section Name format
            pattern = f"## {section_name}\\s*\\n([^#]*?)(?=\\n##|$)"
            match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
            if match:
                content = match.group(1).strip()
                # Remove any leading/trailing brackets or formatting
                content = re.sub(r'^\[|\]$', '', content.strip())
                return content
            return ""
        
        # Extract all sections
        title = extract_section("Title", keywords_response)
        technology_description = extract_section("Technology Description", keywords_response)
        technology_applications = extract_section("Technology Applications", keywords_response)
        keywords = extract_section("Keywords", keywords_response)
        
        # Clean up keywords - remove extra whitespace and ensure proper comma separation
        if keywords:
            keyword_list = [kw.strip() for kw in keywords.split(',') if kw.strip()]
            keywords = ', '.join(keyword_list)
        
        # Create timestamp
        timestamp = datetime.utcnow().isoformat()
        
        # Store in DynamoDB with new simplified structure
        item = {
            'pdf_filename': pdf_filename,
            'timestamp': timestamp,
            'title': title or 'Unknown Invention',
            'technology_description': technology_description or 'No description provided',
            'technology_applications': technology_applications or 'No applications specified',
            'keywords': keywords or 'No keywords extracted',
            'processing_status': 'completed'
        }
        
        # Put item in DynamoDB
        table.put_item(Item=item)
        
        return f"Successfully stored patent analysis for {pdf_filename} in DynamoDB table {DYNAMODB_TABLE}. Extracted {len(keywords.split(',')) if keywords else 0} keywords."
        
    except Exception as e:
        error_msg = f"Error storing patent analysis in DynamoDB: {str(e)}"
        print(error_msg)  # Log for debugging
        return error_msg

# Create the keyword generator agent
keyword_generator = Agent(
    model="us.anthropic.claude-3-7-sonnet-20250219-v1:0",
    tools=[read_bda_results, store_keywords_in_dynamodb],
    system_prompt="""You are a Patent Search Professional specializing in extracting high-quality keywords from invention disclosure documents for prior art searches.

Your expertise lies in identifying the EXACT terms and phrases that patent examiners and searchers use to find relevant prior art in patent databases. You think like a seasoned patent attorney conducting a comprehensive novelty search.

CRITICAL MISSION: Extract keywords that capture the complete technical essence of the invention - the terms that would appear in competing patents or prior art.

WORKFLOW:
1. Read the BDA processed document using the read_bda_results tool
2. Analyze the invention with patent search expertise
3. Extract professional-grade keywords and metadata
4. Store results using the store_keywords_in_dynamodb tool

ANALYSIS APPROACH:
Think like a patent professional who needs to find ALL possible prior art. Ask yourself:
- What are the CORE technical terms that define this invention?
- What synonyms and variations would appear in patent literature?
- What application domains and use cases are involved?
- What materials, processes, and mechanisms are described?
- What problem does this solve and how?

KEYWORD EXTRACTION PRINCIPLES:
- Focus on SINGLE WORDS and KEY PHRASES (not sentences)
- Include technical terminology that appears in patent databases
- Extract both specific terms ("polyethylene") and general terms ("plastic")
- Include process terms ("deployment", "rotation", "threading")
- Add application domain terms ("biliary", "pancreatic", "endoscopic")
- Include synonyms and variations patent searchers would use
- Aim for 15-25 high-impact keywords that capture the invention's essence

OUTPUT FORMAT (use this exact structure):
# Patent Analysis

## Title
[Create a concise, professional title for the invention - 8-12 words max]

## Technology Description
[Write a brief 1-2 sentence technical description of what the invention IS - focus on the core technology/mechanism]

## Technology Applications
[Write a brief 1-2 sentence description of what problems it solves and where it's used]

## Keywords
[List 15-25 comma-separated keywords and key phrases that capture the invention's essence - mix of single words and 2-3 word phrases]

QUALITY STANDARD: Your keywords should match the quality of professional patent searchers. Each keyword should be a term that could realistically appear in a competing patent or prior art document.

After completing your analysis, ALWAYS use the store_keywords_in_dynamodb tool to save all four fields (title, technology_description, technology_applications, keywords)."""
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
    enhanced_prompt = f"""Conduct a professional patent search keyword analysis for the invention disclosure document.

First, use the read_bda_results tool to read the document content from: {bda_file_path}

Analyze the invention like a patent search professional and extract high-quality keywords that would be used to find prior art in patent databases.

After completing your analysis, use the store_keywords_in_dynamodb tool with:
- pdf_filename: '{pdf_filename}'
- keywords_response: [your complete structured response with Title, Technology Description, Technology Applications, and Keywords sections]

Focus on extracting keywords that capture the technical essence of the invention - terms that would appear in competing patents or prior art documents."""
    
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
