#!/usr/bin/env python3
"""
Patent Novelty Assessment Agent using Strands SDK.
Analyzes invention disclosure documents and extracts keywords for patent searches.
Version: ARM64 compatible - Build 3 - Cache Bust
"""

import json
import os
import boto3
from typing import Optional
from botocore.config import Config
from typing import Any, Dict, Optional, List
from pydantic import BaseModel, Field
from bedrock_agentcore.memory import MemoryClient

from strands import Agent, tool
from strands.models.bedrock import BedrockModel
from strands_tools.agent_core_memory import AgentCoreMemoryToolProvider
from bedrock_agentcore.runtime import BedrockAgentCoreApp

# Environment Variables
AWS_REGION = os.getenv('AWS_REGION')
BUCKET_NAME = os.getenv('BUCKET_NAME')
AGENTCORE_MEMORY_ID = os.getenv('AGENTCORE_MEMORY_ID')

# Bedrock client configuration with extended timeout
BEDROCK_CONFIG = Config(
    read_timeout=300,  # 5 minutes for long generations
    connect_timeout=60,
    retries={'max_attempts': 3}
)

class InventionAnalysis(BaseModel):
    """Structure for invention analysis results."""
    title: str = Field(..., description="Invention title")
    summary: str = Field(..., description="Brief invention summary")
    technical_keywords: List[str] = Field(..., description="Technical keywords for patent search")
    problem_solved: str = Field(..., description="Problem the invention solves")
    innovation_points: List[str] = Field(..., description="Key innovation points")

@tool
def read_bda_results(file_path: str) -> Dict[str, Any]:
    """
    Read BDA processing results from S3.
    
    Use this tool to read processed invention disclosure documents from S3.
    The file contains structured JSON data extracted by AWS Bedrock Data Automation.
    
    Args:
        file_path: S3 path to the BDA result.json file (e.g., "temp/docParser/filename-timestamp/job-id/0/standard_output/0/result.json")
    
    Returns:
        Dictionary containing the BDA processed document data with success status
    """
    try:
        s3_client = boto3.client('s3', region_name=AWS_REGION)
        
        response = s3_client.get_object(Bucket=BUCKET_NAME, Key=file_path)
        content = response['Body'].read().decode('utf-8')
        bda_data = json.loads(content)
        
        return {
            "success": True,
            "data": bda_data,
            "message": f"Successfully read BDA results from {file_path}",
            "document_pages": bda_data.get('metadata', {}).get('number_of_pages', 0),
            "elements_count": len(bda_data.get('elements', []))
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "message": f"Failed to read BDA results from {file_path}"
        }

@tool
def analyze_invention_disclosure(bda_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Analyze invention disclosure document from BDA results.
    
    Args:
        bda_data: BDA processed document data
    
    Returns:
        Structured analysis of the invention
    """
    if not bda_data:
        return {"success": False, "error": "No BDA data provided. Please use read_bda_results first."}
    
    try:
        print("Starting analyze_invention_disclosure...")
        
        # Extract document text with timeout protection
        print("Extracting document text...")
        document_text = bda_data.get('document', {}).get('representation', {}).get('text', '')
        print(f"Document text length: {len(document_text)}")
        
        # Extract metadata
        print("Extracting metadata...")
        metadata = bda_data.get('metadata', {})
        print(f"Metadata keys: {list(metadata.keys())}")
        
        # Basic analysis (this would be enhanced with more sophisticated NLP)
        print("Creating analysis...")
        analysis = {
            "document_info": {
                "pages": metadata.get('number_of_pages', 0),
                "file_type": metadata.get('file_type', ''),
                "s3_key": metadata.get('s3_key', '')
            },
            "content_stats": bda_data.get('document', {}).get('statistics', {}),
            "full_text": document_text[:1000] + "..." if len(document_text) > 1000 else document_text,  # Reduced size
            "pages_data": len(bda_data.get('pages', [])),
            "elements_count": len(bda_data.get('elements', []))
        }
        
        print("Analysis completed successfully")
        return {
            "success": True,
            "analysis": analysis,
            "message": "Successfully analyzed invention disclosure"
        }
    except Exception as e:
        print(f"Error in analyze_invention_disclosure: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "message": "Failed to analyze invention disclosure"
        }

@tool
def extract_patent_keywords(document_text: str, invention_title: str = "") -> Dict[str, Any]:
    """
    Extract relevant keywords for patent search from invention text.
    
    Use this tool to generate patent search keywords from invention disclosure content.
    This helps identify relevant prior art and assess novelty.
    
    Args:
        document_text: Full text of the invention disclosure
        invention_title: Title of the invention (optional)
    
    Returns:
        Dictionary containing extracted keywords and search strategies
    """
    try:
        # Simple keyword extraction (enhanced approach)
        text_lower = document_text.lower()
        
        # Technical terms commonly found in patents
        technical_indicators = [
            'method', 'system', 'device', 'apparatus', 'composition',
            'algorithm', 'process', 'technique', 'mechanism', 'structure',
            'medical', 'stent', 'deployment', 'spiral', 'threaded'
        ]
        
        # Extract potential keywords
        keywords = []
        if invention_title:
            title_words = [word.strip('.,!?()[]{}') for word in invention_title.split() if len(word) > 3]
            keywords.extend(title_words)
        
        # Find technical terms in text
        found_technical = [term for term in technical_indicators if term in text_lower]
        keywords.extend(found_technical)
        
        # Extract key phrases (simple approach)
        key_phrases = []
        if 'medical device' in text_lower:
            key_phrases.append('medical device')
        if 'stent' in text_lower and 'deployment' in text_lower:
            key_phrases.append('stent deployment')
        if 'spiral' in text_lower or 'threaded' in text_lower:
            key_phrases.append('spiral mechanism')
            
        # Basic keyword combinations
        keyword_combinations = []
        if len(keywords) >= 2:
            for i in range(min(len(keywords)-1, 5)):
                keyword_combinations.append(f"{keywords[i]} {keywords[i+1]}")
        
        result = {
            "primary_keywords": list(set(keywords[:10])),  # Top 10 unique keywords
            "key_phrases": key_phrases,
            "keyword_combinations": keyword_combinations[:5],  # Top 5 combinations
            "technical_terms": found_technical,
            "search_strategy": {
                "broad_search": list(set(keywords[:5])),
                "specific_search": key_phrases + keyword_combinations[:3]
            }
        }
        
        return {
            "success": True,
            "keywords": result,
            "message": f"Successfully extracted {len(result['primary_keywords'])} keywords and {len(result['key_phrases'])} key phrases"
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "message": "Failed to extract keywords"
        }

@tool
def save_analysis_results(analysis_data: Dict[str, Any], output_path: str) -> Dict[str, Any]:
    """
    Save analysis results to S3.
    
    Args:
        analysis_data: Analysis results to save
        output_path: S3 path where to save the results (e.g., "temp/docParser/filename-timestamp/agent_analysis/")
    
    Returns:
        Status of the save operation
    """
    try:
        s3_client = boto3.client('s3', region_name=AWS_REGION)
        
        # Save different types of analysis
        files_saved = []
        
        # Save invention summary
        if 'invention_summary' in analysis_data:
            summary_key = f"{output_path}invention_summary.json"
            s3_client.put_object(
                Bucket=BUCKET_NAME,
                Key=summary_key,
                Body=json.dumps(analysis_data['invention_summary'], indent=2),
                ContentType='application/json'
            )
            files_saved.append(summary_key)
        
        # Save keywords
        if 'keywords' in analysis_data:
            keywords_key = f"{output_path}keywords.json"
            s3_client.put_object(
                Bucket=BUCKET_NAME,
                Key=keywords_key,
                Body=json.dumps(analysis_data['keywords'], indent=2),
                ContentType='application/json'
            )
            files_saved.append(keywords_key)
        
        # Save complete analysis
        complete_key = f"{output_path}complete_analysis.json"
        s3_client.put_object(
            Bucket=BUCKET_NAME,
            Key=complete_key,
            Body=json.dumps(analysis_data, indent=2),
            ContentType='application/json'
        )
        files_saved.append(complete_key)
        
        return {
            "success": True,
            "files_saved": files_saved,
            "message": f"Successfully saved analysis results to {len(files_saved)} files"
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "message": "Failed to save analysis results"
        }

class PatentNoveltyAgent:
    """Patent Novelty Assessment Agent for analyzing invention disclosures."""
    
    _session_agents: Dict[str, Agent] = {}

    def __init__(self, session_id: Optional[str] = None):
        self.session_id = session_id
        self.memory_client = MemoryClient(region_name=AWS_REGION) if AWS_REGION else None
        self.memory_id = AGENTCORE_MEMORY_ID

        # Create agent
        if session_id and session_id not in self._session_agents:
            self._session_agents[session_id] = self._create_agent()
        
        self.agent = self._session_agents.get(session_id) if session_id else self._create_agent()
    
    def _create_agent(self) -> Agent:
        """Create a new Agent instance."""
        tools = [
            read_bda_results,
            analyze_invention_disclosure,
            extract_patent_keywords,
            save_analysis_results
        ]

        # Create BedrockModel with extended timeout configuration
        bedrock_model = BedrockModel(
            boto_client_config=BEDROCK_CONFIG
        )

        return Agent(
            model=bedrock_model,
            tools=tools,
            system_prompt=(
                "You are a Patent Novelty Assessment Agent that analyzes invention disclosure documents.\n\n"
                "Available Tools:\n"
                "• read_bda_results: Read processed documents from S3\n"
                "• analyze_invention_disclosure: Analyze invention content\n"
                "• extract_patent_keywords: Generate patent search keywords\n"
                "• save_analysis_results: Store analysis results to S3\n\n"
                "Workflow:\n"
                "1. Use read_bda_results to get the document data from S3\n"
                "2. Use analyze_invention_disclosure to understand the invention\n"
                "3. Use extract_patent_keywords to generate search terms\n"
                "4. Use save_analysis_results to store the complete analysis\n\n"
                "Always follow this sequence and provide clear, structured analysis."
            )
        )

async def handle_agent_request(payload):
    """Handle agent request for patent novelty assessment."""
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            payload = {"prompt": payload}
    
    prompt = payload.get("prompt")
    session_id = payload.get("session_id")
    bda_file_path = payload.get("bda_file_path")
    
    if not prompt:
        yield {"error": "Error: 'prompt' is required."}
        return
    
    try:
        agent = PatentNoveltyAgent(session_id=session_id)

        # Add BDA file path to prompt if provided
        if bda_file_path:
            prompt += f"\n\nBDA File Path: {bda_file_path}"

        # Stream the response
        final_response = ""
        async for event in agent.agent.stream_async(prompt):
            if "data" in event:
                yield {"thinking": event["data"]}
            elif "message" in event and isinstance(event["message"], dict):
                if "content" in event["message"]:
                    for content in event["message"]["content"]:
                        if "text" in content:
                            yield {"response": content["text"]}
                            final_response = content["text"]
            elif "current_tool_use" in event:
                tool_info = event["current_tool_use"]
                if "name" in tool_info:
                    tool_data = {"tool_name": tool_info["name"]}
                    if "input" in tool_info:
                        tool_data["tool_input"] = tool_info["input"]
                    yield tool_data
            elif "error" in event:
                yield {"error": event["error"]}

        if final_response:
            yield {"final_result": final_response}
            
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
