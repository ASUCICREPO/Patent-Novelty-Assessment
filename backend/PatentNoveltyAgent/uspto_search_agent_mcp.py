#!/usr/bin/env python3
"""
USPTO Patent Search Agent using direct requests to Gateway.
"""

import json
import os
import boto3
import requests
from datetime import datetime
from decimal import Decimal
from typing import Dict, Any, List
from strands import Agent, tool
from strands.tools.mcp.mcp_client import MCPClient
from mcp.client.streamable_http import streamablehttp_client
from bedrock_agentcore.runtime import BedrockAgentCoreApp

# Environment Variables
AWS_REGION = os.getenv('AWS_REGION', 'us-west-2')
KEYWORDS_TABLE = os.getenv('KEYWORDS_TABLE_NAME')
RESULTS_TABLE = os.getenv('RESULTS_TABLE_NAME')

# Gateway Configuration
CLIENT_ID = os.environ.get('GATEWAY_CLIENT_ID')
CLIENT_SECRET = os.environ.get('GATEWAY_CLIENT_SECRET')
TOKEN_URL = os.environ.get('GATEWAY_TOKEN_URL')
GATEWAY_URL = os.environ.get('GATEWAY_URL')

# Validate all required environment variables
missing_vars = []
if not CLIENT_ID:
    missing_vars.append('GATEWAY_CLIENT_ID')
if not CLIENT_SECRET:
    missing_vars.append('GATEWAY_CLIENT_SECRET')
if not TOKEN_URL:
    missing_vars.append('GATEWAY_TOKEN_URL')
if not GATEWAY_URL:
    missing_vars.append('GATEWAY_URL')

if missing_vars:
    print(f"WARNING: Missing environment variables: {', '.join(missing_vars)}. USPTO search will fail.")

def fetch_access_token():
    """Get OAuth access token for Gateway."""
    try:
        if not all([CLIENT_ID, CLIENT_SECRET, TOKEN_URL]):
            raise Exception("Missing required environment variables: GATEWAY_CLIENT_ID, GATEWAY_CLIENT_SECRET, GATEWAY_TOKEN_URL")
            
        print(f"Fetching token from: {TOKEN_URL}")
        print(f"Client ID: {CLIENT_ID}")
        
        response = requests.post(
            TOKEN_URL,
            data=f"grant_type=client_credentials&client_id={CLIENT_ID}&client_secret={CLIENT_SECRET}",
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            timeout=30
        )
        
        print(f"Token response status: {response.status_code}")
        
        if response.status_code != 200:
            raise Exception(f"Token request failed: {response.status_code} - {response.text}")
        
        token_data = response.json()
        access_token = token_data.get('access_token')
        
        if not access_token:
            raise Exception(f"No access token in response: {token_data}")
        
        return access_token
        
    except Exception as e:
        print(f"Error fetching access token: {e}")
        raise

def create_streamable_http_transport(mcp_url: str, access_token: str):
    return streamablehttp_client(mcp_url, headers={"Authorization": f"Bearer {access_token}"})

def get_full_tools_list(client):
    """List tools with pagination support"""
    more_tools = True
    tools = []
    pagination_token = None
    while more_tools:
        tmp_tools = client.list_tools_sync(pagination_token=pagination_token)
        tools.extend(tmp_tools)
        if tmp_tools.pagination_token is None:
            more_tools = False
        else:
            more_tools = True 
            pagination_token = tmp_tools.pagination_token
    return tools

@tool
def read_keywords_from_dynamodb(pdf_filename: str) -> Dict[str, Any]:
    """Read patent keywords from DynamoDB."""
    try:
        dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
        table = dynamodb.Table(KEYWORDS_TABLE)
        
        response = table.query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key('pdf_filename').eq(pdf_filename),
            ScanIndexForward=False,
            Limit=1
        )
        
        if not response['Items']:
            return {"error": f"No keywords found for PDF: {pdf_filename}"}
        
        keywords_data = response['Items'][0]
        return {
            "pdf_filename": keywords_data.get('pdf_filename'),
            "application_use": keywords_data.get('application_use', ''),
            "mechanism_composition": keywords_data.get('mechanism_composition', ''),
            "synonyms": keywords_data.get('synonyms', ''),
            "patent_classifications": keywords_data.get('patent_classifications', ''),
            "timestamp": keywords_data.get('timestamp'),
            "processing_status": keywords_data.get('processing_status')
        }
        
    except Exception as e:
        return {"error": f"Error reading keywords: {str(e)}"}

@tool
def search_uspto_patents(search_query: str, limit: int = 25) -> List[Dict[str, Any]]:
    """Search USPTO patents via Gateway using Strands MCP client."""
    try:
        # Get access token
        access_token = fetch_access_token()
        print(f"Got access token: {access_token[:20]}...")
        
        # Create MCP client using your working pattern
        mcp_client = MCPClient(lambda: create_streamable_http_transport(GATEWAY_URL, access_token))
        
        with mcp_client:
            # Get tools with pagination
            tools = get_full_tools_list(mcp_client)
            print(f"Available tools: {[tool.tool_name for tool in tools] if tools else 'None'}")
            
            if not tools:
                return []
            
            # Find USPTO search tool
            search_tool = None
            for tool in tools:
                if 'searchPatentsSimple' in tool.tool_name:
                    search_tool = tool
                    break
            
            if not search_tool:
                print("No USPTO search tool found")
                return []
            
            print(f"Using tool: {search_tool.tool_name}")
            
            # Call the tool with correct signature
            result = mcp_client.call_tool_sync(
                name=search_tool.tool_name,
                arguments={"q": search_query, "limit": limit},
                tool_use_id=f"search-{hash(search_query)}"
            )
            
            print(f"Tool call result type: {type(result)}")
            
            if result and isinstance(result, dict) and 'content' in result:
                content = result['content']
                if isinstance(content, list) and len(content) > 0:
                    text_content = content[0].get('text', '') if isinstance(content[0], dict) else str(content[0])
                    print(f"Content preview: {text_content[:200]}...")
                    
                    try:
                        data = json.loads(text_content)
                        patents = data.get("patentFileWrapperDataBag", [])
                        
                        if patents:
                            print(f"✅ Found {len(patents)} real USPTO patents!")
                            
                            # Pre-process patents to ensure they have the fields store_patent_analysis expects
                            processed_patents = []
                            for patent in patents:
                                app_meta = patent.get('applicationMetaData', {})
                                
                                # Create a processed patent with all the fields pre-extracted
                                processed_patent = {
                                    'applicationNumberText': patent.get('applicationNumberText', 'unknown'),
                                    'applicationMetaData': app_meta,
                                    'search_query_used': search_query,
                                    'relevance_score': 0.8,  # Default relevance score
                                    'matching_keywords': search_query
                                }
                                processed_patents.append(processed_patent)
                            
                            return processed_patents
                        else:
                            print(f"⚠️ No patents found in response")
                            return []
                            
                    except json.JSONDecodeError as je:
                        print(f"JSON decode error: {je}")
                        return []
                else:
                    print("No valid content in result")
                    return []
            else:
                print(f"No content in result: {result}")
                return []
                
    except Exception as e:
        print(f"Error searching USPTO: {e}")
        import traceback
        traceback.print_exc()
        return []

@tool
def calculate_relevance_score(patent_data: Dict, original_keywords: Dict) -> float:
    """Calculate relevance score between patent and keywords."""
    try:
        score = 0.0
        total_weight = 0.0
        
        patent_text = f"{patent_data.get('title', '')} {patent_data.get('abstract', '')}"
        patent_text_lower = patent_text.lower()
        
        weights = {
            'mechanism_composition': 0.4,
            'application_use': 0.3,
            'synonyms': 0.2,
            'patent_classifications': 0.1
        }
        
        for category, weight in weights.items():
            keywords = original_keywords.get(category, '')
            if keywords:
                keyword_list = [k.strip() for k in keywords.split(',') if k.strip()]
                matches = sum(1 for keyword in keyword_list if keyword.lower() in patent_text_lower)
                category_score = min(matches / len(keyword_list), 1.0) if keyword_list else 0.0
                score += category_score * weight
                total_weight += weight
        
        return round(score / total_weight if total_weight > 0 else 0.0, 3)
        
    except Exception as e:
        print(f"Error calculating relevance score: {str(e)}")
        return 0.0

@tool
def store_patent_analysis(pdf_filename: str, patent_number: str, patent_title: str, inventor: str, assignee: str, relevance_score: float, search_query: str) -> str:
    """Store individual patent analysis result in DynamoDB."""
    try:
        dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
        table = dynamodb.Table(RESULTS_TABLE)
        
        timestamp = datetime.utcnow().isoformat()
        
        item = {
            'pdf_filename': pdf_filename,
            'patent_number': patent_number,
            'patent_title': patent_title,
            'patent_inventors': inventor,
            'patent_assignee': assignee,
            'relevance_score': Decimal(str(relevance_score)),
            'search_strategy_used': search_query,
            'search_timestamp': timestamp,
            'uspto_url': f"https://patents.uspto.gov/patent/{patent_number}",
            'patent_abstract': f"Patent analysis for {patent_title}",
            'rank_position': 1,
            'filing_date': '',
            'publication_date': '',
            'patent_status': '',
            'matching_keywords': search_query,
            'total_results_found': 1,
            'search_strategies_tried': [search_query],
            'patent_class': '',
            'patent_subclass': '',
            'examiner': '',
            'publication_number': ''
        }
        
        table.put_item(Item=item)
        return f"Successfully stored patent {patent_number}: {patent_title}"
        
    except Exception as e:
        return f"Error storing patent {patent_number}: {str(e)}"

# Create the USPTO search agent
uspto_search_agent = Agent(
    model="us.anthropic.claude-3-7-sonnet-20250219-v1:0",
    tools=[read_keywords_from_dynamodb, search_uspto_patents, calculate_relevance_score, store_patent_analysis],
    system_prompt="""You are a USPTO Patent Search Expert. Execute this workflow EXACTLY ONCE:

1. Read keywords from DynamoDB using the PDF filename
2. Execute 2-3 strategic USPTO searches using different keyword combinations
3. Score and select the top 5 most relevant patents
4. Store results in DynamoDB

CRITICAL RULES:
- Execute each tool call only once per search strategy
- If a search fails, continue with the next strategy
- Maximum 3 search attempts total
- Always store results even if searches fail
- Do not retry failed searches

SEARCH STRATEGIES:
1. Core mechanism terms (e.g., "spiraled stent", "threaded deployment")
2. Application terms (e.g., "biliary duct", "pancreatic stricture")
3. Combined technical + application terms

Complete the workflow efficiently and provide a final summary."""
)

async def handle_uspto_search_request(payload):
    """Handle USPTO patent search request."""
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            payload = {"pdf_filename": payload}
    
    pdf_filename = payload.get("pdf_filename")
    
    if not pdf_filename:
        yield {"error": "Error: 'pdf_filename' is required."}
        return
    
    enhanced_prompt = f"""Search for patents similar to the invention in PDF: {pdf_filename}

INSTRUCTIONS:
1. Read keywords from DynamoDB for this PDF
2. Analyze the invention's technical aspects
3. Execute multiple strategic patent searches via Gateway
4. Score and rank results by relevance
5. Select top 5 most relevant patents
6. Store results with comprehensive metadata

Focus on patents that could impact novelty assessment."""
    
    try:
        full_response = ""
        search_metadata = {"strategies_used": [], "total_results": 0}
        
        async for event in uspto_search_agent.stream_async(enhanced_prompt):
            if "data" in event:
                full_response += event["data"]
            elif "current_tool_use" in event and event["current_tool_use"].get("name"):
                tool_name = event["current_tool_use"]["name"]
                yield {"tool_name": tool_name}
                if tool_name == "search_uspto_patents":
                    search_metadata["strategies_used"].append(tool_name)
            elif "error" in event:
                yield {"error": event["error"]}
                return
        
        if full_response.strip():
            yield {"response": full_response, "search_metadata": search_metadata}
        else:
            yield {"error": "No response generated"}
                
    except Exception as e:
        yield {"error": f"Error processing request: {str(e)}"}

app = BedrockAgentCoreApp()

@app.entrypoint
async def invoke(payload: Dict[str, Any]):
    """AgentCore streaming entrypoint."""
    async for event in handle_uspto_search_request(payload):
        yield event

if __name__ == "__main__":
    app.run()
