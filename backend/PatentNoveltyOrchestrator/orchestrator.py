#!/usr/bin/env python3
"""
Patent Novelty Orchestrator Agent. Routes requests to appropriate agents based on action type.
"""
import json
import os
import boto3
import requests
import re
import time
from datetime import datetime
from decimal import Decimal
from typing import Dict, Any, List
from strands import Agent, tool
from strands.tools.mcp.mcp_client import MCPClient
from mcp.client.streamable_http import streamablehttp_client
from bedrock_agentcore.runtime import BedrockAgentCoreApp

# Environment Variables
AWS_REGION = os.getenv('AWS_REGION', 'us-west-2')
BUCKET_NAME = os.getenv('BUCKET_NAME')
KEYWORDS_TABLE = os.getenv('KEYWORDS_TABLE_NAME')
RESULTS_TABLE = os.getenv('RESULTS_TABLE_NAME')
ARTICLES_TABLE = os.getenv('ARTICLES_TABLE_NAME')

# Gateway Configuration for PatentView Search
PATENTVIEW_CLIENT_ID = os.environ.get('PATENTVIEW_CLIENT_ID')
PATENTVIEW_CLIENT_SECRET = os.environ.get('PATENTVIEW_CLIENT_SECRET')
PATENTVIEW_TOKEN_URL = os.environ.get('PATENTVIEW_TOKEN_URL')
PATENTVIEW_GATEWAY_URL = os.environ.get('PATENTVIEW_GATEWAY_URL')

# Gateway Configuration for Semantic Scholar Search
SEMANTIC_SCHOLAR_CLIENT_ID = os.environ.get('SEMANTIC_SCHOLAR_CLIENT_ID')
SEMANTIC_SCHOLAR_CLIENT_SECRET = os.environ.get('SEMANTIC_SCHOLAR_CLIENT_SECRET')
SEMANTIC_SCHOLAR_TOKEN_URL = os.environ.get('SEMANTIC_SCHOLAR_TOKEN_URL')
SEMANTIC_SCHOLAR_GATEWAY_URL = os.environ.get('SEMANTIC_SCHOLAR_GATEWAY_URL')

# Validate PatentView Gateway environment variables
patentview_missing_vars = []
if not PATENTVIEW_CLIENT_ID:
    patentview_missing_vars.append('PATENTVIEW_CLIENT_ID')
if not PATENTVIEW_CLIENT_SECRET:
    patentview_missing_vars.append('PATENTVIEW_CLIENT_SECRET')
if not PATENTVIEW_TOKEN_URL:
    patentview_missing_vars.append('PATENTVIEW_TOKEN_URL')
if not PATENTVIEW_GATEWAY_URL:
    patentview_missing_vars.append('PATENTVIEW_GATEWAY_URL')

if patentview_missing_vars:
    print(f"WARNING: Missing PatentView environment variables: {', '.join(patentview_missing_vars)}. PatentView search will fail.")

# Validate Semantic Scholar Gateway environment variables - FAIL FAST
semantic_scholar_missing_vars = []
if not SEMANTIC_SCHOLAR_CLIENT_ID:
    semantic_scholar_missing_vars.append('SEMANTIC_SCHOLAR_CLIENT_ID')
if not SEMANTIC_SCHOLAR_CLIENT_SECRET:
    semantic_scholar_missing_vars.append('SEMANTIC_SCHOLAR_CLIENT_SECRET')
if not SEMANTIC_SCHOLAR_TOKEN_URL:
    semantic_scholar_missing_vars.append('SEMANTIC_SCHOLAR_TOKEN_URL')
if not SEMANTIC_SCHOLAR_GATEWAY_URL:
    semantic_scholar_missing_vars.append('SEMANTIC_SCHOLAR_GATEWAY_URL')

if semantic_scholar_missing_vars:
    raise Exception(f"CRITICAL: Missing required Semantic Scholar environment variables: {', '.join(semantic_scholar_missing_vars)}. Cannot start orchestrator without these variables.")

# =============================================================================
# KEYWORD GENERATOR TOOLS
# =============================================================================

@tool
def read_bda_results(file_path: str) -> str:
    """
    Read BDA processing results from S3 and return the full document content.
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
    """
    try:
        # Initialize DynamoDB resource
        dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
        table = dynamodb.Table(KEYWORDS_TABLE)
        
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
        
        return f"Successfully stored patent analysis for {pdf_filename} in DynamoDB table {KEYWORDS_TABLE}. Extracted {len(keywords.split(',')) if keywords else 0} keywords."
        
    except Exception as e:
        error_msg = f"Error storing patent analysis in DynamoDB: {str(e)}"
        print(error_msg)  # Log for debugging
        return error_msg

# =============================================================================
# PatentView SEARCH TOOLS
# =============================================================================

def fetch_patentview_access_token():
    """Get OAuth access token for PatentView Gateway."""
    try:
        if not all([PATENTVIEW_CLIENT_ID, PATENTVIEW_CLIENT_SECRET, PATENTVIEW_TOKEN_URL]):
            raise Exception("Missing required PatentView environment variables: PATENTVIEW_CLIENT_ID, PATENTVIEW_CLIENT_SECRET, PATENTVIEW_TOKEN_URL")
            
        print(f"Fetching PatentView token from: {PATENTVIEW_TOKEN_URL}")
        print(f"PatentView Client ID: {PATENTVIEW_CLIENT_ID}")
        
        response = requests.post(
            PATENTVIEW_TOKEN_URL,
            data=f"grant_type=client_credentials&client_id={PATENTVIEW_CLIENT_ID}&client_secret={PATENTVIEW_CLIENT_SECRET}",
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            timeout=30
        )
        
        print(f"PatentView token response status: {response.status_code}")
        
        if response.status_code != 200:
            raise Exception(f"PatentView token request failed: {response.status_code} - {response.text}")
        
        token_data = response.json()
        access_token = token_data.get('access_token')
        
        if not access_token:
            raise Exception(f"No access token in PatentView response: {token_data}")
        
        return access_token
        
    except Exception as e:
        print(f"Error fetching PatentView access token: {e}")
        raise

def create_streamable_http_transport(mcp_url: str, access_token: str):
    """Create streamable HTTP transport for MCP client with OAuth Bearer token."""
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
    """Read patent analysis data from DynamoDB."""
    try:
        dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
        table = dynamodb.Table(KEYWORDS_TABLE)
        
        response = table.query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key('pdf_filename').eq(pdf_filename),
            ScanIndexForward=False,
            Limit=1
        )
        
        if not response['Items']:
            return {"error": f"No patent analysis found for PDF: {pdf_filename}"}
        
        keywords_data = response['Items'][0]
        return {
            "pdf_filename": keywords_data.get('pdf_filename'),
            "title": keywords_data.get('title', ''),
            "technology_description": keywords_data.get('technology_description', ''),
            "technology_applications": keywords_data.get('technology_applications', ''),
            "keywords": keywords_data.get('keywords', ''),
            "timestamp": keywords_data.get('timestamp'),
            "processing_status": keywords_data.get('processing_status')
        }
        
    except Exception as e:
        return {"error": f"Error reading patent analysis: {str(e)}"}

def parse_keywords(keywords_string: str) -> List[Dict[str, Any]]:
    """
    Parse comma-separated keywords and detect multi-word phrases.
    
    Returns list of dicts with 'keyword' and 'is_phrase' fields.
    Example: "lignin, cellulose microbead, ionic liquid" 
    -> [
        {"keyword": "lignin", "is_phrase": False},
        {"keyword": "cellulose microbead", "is_phrase": True},
        {"keyword": "ionic liquid", "is_phrase": True}
    ]
    """
    try:
        if not keywords_string:
            return []
        
        # Split by comma and clean
        raw_keywords = [k.strip() for k in keywords_string.split(',') if k.strip()]
        
        parsed_keywords = []
        for keyword in raw_keywords:
            # Check if multi-word (contains space)
            is_phrase = ' ' in keyword
            parsed_keywords.append({
                "keyword": keyword,
                "is_phrase": is_phrase
            })
        
        print(f"📝 Parsed {len(parsed_keywords)} keywords: {[k['keyword'] for k in parsed_keywords]}")
        return parsed_keywords
        
    except Exception as e:
        print(f"Error parsing keywords: {e}")
        return []

@tool
def search_patents_by_keyword(keyword: str, is_phrase: bool, limit: int = 10) -> Dict[str, Any]:
    """
    Search PatentView for patents matching a single keyword.
    Uses _text_any for both single words and multi-word keywords.
    Sorts by patent_date DESC (newest first).
    """
    try:
        # Build query - always use _text_any for broader results
        query_json = {
            "_text_any": {
                "patent_abstract": keyword
            }
        }
        
        # Fix query syntax (convert arrays to strings if needed)
        fix_patentview_query(query_json)
        
        print(f"🔍 Searching PatentView for keyword: '{keyword}' (phrase={is_phrase})")
        
        # Execute search via gateway
        result = run_patentview_search_via_gateway(
            query_json=query_json,
            limit=limit,
            sort_by=[{"patent_date": "desc"}]  # Newest first
        )
        
        if result.get('success'):
            patents = result.get('patents', [])
            print(f"✅ Found {len(patents)} patents for keyword '{keyword}'")
            
            # Add keyword metadata to each patent
            for patent in patents:
                patent['matched_keyword'] = keyword
                patent['search_type'] = 'phrase' if is_phrase else 'single_word'
            
            return {
                'success': True,
                'keyword': keyword,
                'patents': patents,
                'total_found': len(patents)
            }
        else:
            print(f"❌ Search failed for keyword '{keyword}': {result.get('error')}")
            return {
                'success': False,
                'keyword': keyword,
                'patents': [],
                'error': result.get('error', 'Unknown error')
            }
            
    except Exception as e:
        print(f"Error searching for keyword '{keyword}': {e}")
        return {
            'success': False,
            'keyword': keyword,
            'patents': [],
            'error': str(e)
        }

@tool
def search_all_keywords_and_prefilter(keywords_string: str, top_n: int = 50) -> Dict[str, Any]:
    """
    Orchestrator tool: Parse keywords, search each one, deduplicate, and pre-filter.
    Returns top N patents by citation count, ready for LLM evaluation.
    
    This tool does ALL the search work in one call:
    1. Parses comma-separated keywords (detects multi-word phrases)
    2. Searches each keyword (top 10 newest patents per keyword)
    3. Deduplicates by patent_id
    4. Pre-filters to top N by citation_count
    5. Returns ready-to-evaluate patents
    """
    try:
        print(f"🚀 Starting comprehensive keyword search")
        print(f"   Keywords: {keywords_string}")
        
        # Step 1: Parse keywords
        parsed_keywords = parse_keywords(keywords_string)
        if not parsed_keywords:
            return {
                'success': False,
                'error': 'No valid keywords to search',
                'patents': [],
                'summary': 'No keywords provided'
            }
        
        print(f"📝 Parsed {len(parsed_keywords)} keywords")
        
        # Step 2: Search each keyword
        all_patents = []
        search_summary = []
        
        for kw_info in parsed_keywords:
            keyword = kw_info['keyword']
            is_phrase = kw_info['is_phrase']
            
            print(f"   Searching: '{keyword}' (phrase={is_phrase})")
            result = search_patents_by_keyword(keyword, is_phrase, limit=10)
            
            patents_found = len(result.get('patents', []))
            search_summary.append({
                'keyword': keyword,
                'is_phrase': is_phrase,
                'success': result.get('success', False),
                'patents_found': patents_found
            })
            
            if result.get('success'):
                all_patents.extend(result.get('patents', []))
        
        print(f"🔍 Searched {len(parsed_keywords)} keywords, found {len(all_patents)} total patents")
        
        if not all_patents:
            return {
                'success': False,
                'error': 'No patents found for any keywords',
                'patents': [],
                'search_summary': search_summary
            }
        
        # Step 3: Deduplicate
        unique_patents = deduplicate_patents(all_patents)
        print(f"🔄 After deduplication: {len(unique_patents)} unique patents")
        
        # Step 4: Pre-filter by citation count
        top_patents = prefilter_by_citations(unique_patents, top_n=top_n)
        print(f"📊 Pre-filtered to top {len(top_patents)} patents by citation count")
        
        return {
            'success': True,
            'patents': top_patents,
            'total_searched': len(all_patents),
            'unique_count': len(unique_patents),
            'prefiltered_count': len(top_patents),
            'keywords_searched': len(parsed_keywords),
            'search_summary': search_summary
        }
        
    except Exception as e:
        print(f"❌ Error in search_all_keywords_and_prefilter: {e}")
        import traceback
        traceback.print_exc()
        return {
            'success': False,
            'error': str(e),
            'patents': []
        }

def deduplicate_patents(all_patents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Deduplicate patents by patent_id, keeping first occurrence.
    Tracks which keywords matched each patent.
    """
    try:
        unique_patents = {}
        
        for patent in all_patents:
            patent_id = patent.get('patent_id')
            if not patent_id:
                continue
            
            if patent_id not in unique_patents:
                # First occurrence - keep it
                unique_patents[patent_id] = patent
                # Initialize matched_keywords list
                matched_kw = patent.get('matched_keyword', '')
                patent['matched_keywords'] = [matched_kw] if matched_kw else []
                # Store as comma-separated string for DynamoDB
                patent['matching_keywords'] = matched_kw
            else:
                # Duplicate - add keyword to existing patent's list
                existing = unique_patents[patent_id]
                keyword = patent.get('matched_keyword', '')
                if keyword and keyword not in existing.get('matched_keywords', []):
                    if 'matched_keywords' not in existing:
                        existing['matched_keywords'] = []
                    existing['matched_keywords'].append(keyword)
                    # Update comma-separated string
                    existing['matching_keywords'] = ', '.join(existing['matched_keywords'])
        
        result = list(unique_patents.values())
        print(f"🔄 Deduplicated: {len(all_patents)} → {len(result)} unique patents")
        return result
        
    except Exception as e:
        print(f"Error deduplicating patents: {e}")
        return all_patents

def prefilter_by_citations(patents: List[Dict[str, Any]], top_n: int = 50) -> List[Dict[str, Any]]:
    """
    Pre-filter patents by citation count to reduce LLM evaluation load.
    Keeps top N most cited patents (most impactful prior art).
    """
    try:
        if len(patents) <= top_n:
            print(f"✅ {len(patents)} patents (no pre-filtering needed)")
            return patents
        
        # Sort by citation count descending
        sorted_patents = sorted(
            patents,
            key=lambda x: x.get('citation_count', 0),
            reverse=True
        )
        
        # Keep top N
        filtered = sorted_patents[:top_n]
        
        print(f"📊 Pre-filtered: {len(patents)} → {len(filtered)} patents (top {top_n} by citations)")
        print(f"   Citation range: {filtered[0].get('citation_count', 0)} (max) to {filtered[-1].get('citation_count', 0)} (min)")
        
        return filtered
        
    except Exception as e:
        print(f"Error pre-filtering patents: {e}")
        return patents[:top_n]  # Fallback to simple slice

def run_patentview_search_via_gateway(query_json: Dict, limit: int = 10, sort_by: List[Dict] = None) -> Dict[str, Any]:
    """
    Execute PatentView search via MCP Gateway.
    Simple wrapper for direct keyword searches.
    """
    try:
        # Get OAuth access token
        access_token = fetch_patentview_access_token()
        
        # Create MCP client
        mcp_client = MCPClient(lambda: create_streamable_http_transport(PATENTVIEW_GATEWAY_URL, access_token))
        
        with mcp_client:
            # Get available tools from MCP gateway
            tools = get_full_tools_list(mcp_client)
            
            # Find the PatentView search tool
            search_tool = None
            for tool in tools:
                tool_name = tool.tool_name if hasattr(tool, 'tool_name') else str(tool.name)
                # Look for PatentView search tool (various possible names)
                if 'searchPatentsPatentView' in tool_name or 'patent-view___searchPatentsPatentView' in tool_name:
                    search_tool = tool
                    break
            
            if not search_tool:
                print(f"❌ PatentView search tool not found. Available tools: {[t.tool_name if hasattr(t, 'tool_name') else str(t.name) for t in tools[:5]]}")
                return {
                    'success': False,
                    'patents': [],
                    'error': 'PatentView search tool not available in MCP gateway'
                }
            
            tool_name = search_tool.tool_name if hasattr(search_tool, 'tool_name') else str(search_tool.name)
            print(f"✅ Using PatentView tool: {tool_name}")
            
            # Build search parameters
            search_params = {
                "q": json.dumps(query_json),
                "f": json.dumps([
                    "patent_id",
                    "patent_title",
                    "patent_abstract",
                    "patent_date",
                    "patent_num_times_cited_by_us_patents",  # Forward citations
                    "patent_num_us_patents_cited",            # Backward citations
                    "patent_num_foreign_documents_cited",     # Foreign citations
                    "inventors.inventor_name_first",
                    "inventors.inventor_name_last",
                    "assignees.assignee_organization",
                    "assignees.assignee_individual_name_first",
                    "assignees.assignee_individual_name_last"
                ]),
                "o": json.dumps({"size": limit})
            }
            
            if sort_by:
                search_params["s"] = json.dumps(sort_by)
            
            print(f"🔍 Query: {json.dumps(query_json)}")
            
            # Execute search with correct tool name
            result = mcp_client.call_tool_sync(
                name=tool_name,
                arguments=search_params,
                tool_use_id=f"patentview-search-{hash(json.dumps(query_json))}"
            )
            
            if result and 'content' in result:
                response_text = result['content'][0].get('text', '{}')
                response_data = json.loads(response_text)
                
                patents = response_data.get('patents', [])
                total_hits = response_data.get('total_hits', 0)
                
                print(f"📊 PatentView response: {len(patents)} patents returned, {total_hits} total hits")
                
                # Extract citation counts
                for patent in patents:
                    patent['citation_count'] = patent.get('patent_num_times_cited_by_us_patents', 0)
                
                return {
                    'success': True,
                    'patents': patents,
                    'total_hits': total_hits
                }
            else:
                print(f"❌ No content in MCP response: {result}")
                return {
                    'success': False,
                    'patents': [],
                    'error': 'No content in MCP response'
                }
                
    except Exception as e:
        print(f"❌ PatentView gateway search error: {e}")
        import traceback
        traceback.print_exc()
        return {
            'success': False,
            'patents': [],
            'error': str(e)
        }

def fix_patentview_query(query_json: Dict) -> None:
    """
    Fix common PatentView query syntax issues IN-PLACE.
    
    Key fix: Text operators (_text_any, _text_all, _text_phrase) require STRING values, not arrays.
    Example: {"_text_any": {"patent_title": ["word1", "word2"]}} 
          -> {"_text_any": {"patent_title": "word1 word2"}}
    """
    text_operators = ['_text_any', '_text_all', '_text_phrase']
    
    def fix_recursive(obj):
        if isinstance(obj, dict):
            for key, value in list(obj.items()):
                if key in text_operators and isinstance(value, dict):
                    # Fix text operator field values - convert arrays to strings
                    for field, field_value in list(value.items()):
                        if isinstance(field_value, list):
                            # Convert array to space-separated string
                            obj[key][field] = ' '.join(str(item) for item in field_value)
                            print(f"🔧 Fixed {key}.{field}: array -> '{obj[key][field]}'")
                elif isinstance(value, (dict, list)):
                    fix_recursive(value)
        elif isinstance(obj, list):
            for item in obj:
                if isinstance(item, dict):
                    fix_recursive(item)
    
    try:
        fix_recursive(query_json)
    except Exception as e:
        print(f"Query fix error: {e}")

def validate_patentview_query(query_json: Dict) -> bool:
    """Validate and fix PatentView query syntax."""
    try:
        if not isinstance(query_json, dict):
            return False
        
        # Fix the query in-place before validation
        fix_patentview_query(query_json)
        return True
        
    except Exception as e:
        print(f"Query validation error: {e}")
        return False

@tool
def evaluate_patent_relevance_llm(patent_data: Dict[str, Any], invention_context: Dict[str, Any]) -> Dict[str, Any]:
    """Evaluate patent relevance using LLM for semantic analysis and prior art assessment."""
    try:
        # Extract patent information
        patent_id = patent_data.get('patent_id', 'unknown')
        patent_title = patent_data.get('patent_title', 'Unknown Title')
        patent_abstract = patent_data.get('patent_abstract', '')
        grant_date = patent_data.get('patent_date', '')
        
        # Extract inventor names
        inventors = patent_data.get('inventors', [])
        inventor_names = []
        for inv in inventors[:3]:  # Show first 3 inventors
            first = inv.get('inventor_name_first', '')
            last = inv.get('inventor_name_last', '')
            if first or last:
                inventor_names.append(f"{first} {last}".strip())
        
        # Extract assignee names
        assignees = patent_data.get('assignees', [])
        assignee_names = []
        for asg in assignees:
            org = asg.get('assignee_organization', '')
            if org:
                assignee_names.append(org)
            else:
                first = asg.get('assignee_individual_name_first', '')
                last = asg.get('assignee_individual_name_last', '')
                if first or last:
                    assignee_names.append(f"{first} {last}".strip())
        
        # Citation data
        forward_citations = patent_data.get('patent_num_times_cited_by_us_patents', 0)
        backward_citations = patent_data.get('patent_num_us_patents_cited', 0)
        citation_count = patent_data.get('citation_count', forward_citations)
        
        # Extract invention context
        invention_title = invention_context.get('title', 'Unknown Invention')
        tech_description = invention_context.get('technology_description', '')
        tech_applications = invention_context.get('technology_applications', '')
        keywords = invention_context.get('keywords', '')
        
        # Skip patents without abstracts
        if not patent_abstract or len(patent_abstract.strip()) < 50:
            print(f"Patent {patent_id} lacks sufficient abstract content")
            return {
                'overall_relevance_score': 0.2,
                'key_differences': ['Insufficient patent abstract for analysis'],
                'examiner_notes': 'Patent lacks sufficient abstract content for meaningful relevance assessment'
            }
        
        # Create LLM prompt for patent relevance evaluation
        evaluation_prompt = f"""You are a patent examiner evaluating prior art relevance for novelty assessment.

        INVENTION UNDER EXAMINATION:
        Title: {invention_title}
        Technology: {tech_description}
        Applications: {tech_applications}
        Key Technologies: {keywords}

        PRIOR ART PATENT:
        Patent ID: {patent_id}
        Title: {patent_title}
        Abstract: {patent_abstract}
        Grant Date: {grant_date}
        Inventors: {', '.join(inventor_names) if inventor_names else 'Unknown'}
        Assignee: {', '.join(assignee_names) if assignee_names else 'Unknown'}
        Forward Citations (cited by others): {forward_citations}
        Backward Citations (cites others): {backward_citations}

        PRIOR ART ANALYSIS:
        Evaluate this patent's relevance for novelty assessment:

        1. TECHNICAL OVERLAP ANALYSIS:
        - Core technology similarity (0-10 scale)
        - Method/process similarity (0-10 scale)
        - System architecture similarity (0-10 scale)
        - Component/material overlap (0-10 scale)

        2. NOVELTY IMPACT ASSESSMENT:
        - Does this patent disclose the same invention? (Yes/No)
        - What specific features overlap? (List)
        - What features are different? (List)
        - Could this patent be cited in a rejection? (Yes/No/Maybe)

        3. PRIOR ART STRENGTH:
        - Publication date vs invention date
        - Patent status (granted/published/expired)
        - Citation impact in the field
        - Assignee credibility in the domain

        RESPOND IN THIS EXACT JSON FORMAT:
        {{
            "overall_relevance_score": 0.0-1.0,
            "key_differences": ["list of differentiating features"],
            "examiner_notes": "detailed analysis for patent examiner"
        }}

        Be precise and focus specifically on patent novelty implications."""

        # Make LLM call with retry logic
        max_retries = 3
        for attempt in range(max_retries):
            try:
                bedrock_client = boto3.client('bedrock-runtime', region_name=AWS_REGION)
                request_body = {
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 1500,
                    "messages": [
                        {
                            "role": "user",
                            "content": evaluation_prompt
                        }
                    ]
                }
                
                response = bedrock_client.invoke_model(
                    modelId="us.anthropic.claude-3-7-sonnet-20250219-v1:0",
                    body=json.dumps(request_body)
                )
                
                response_body = json.loads(response['body'].read())
                llm_response = response_body['content'][0]['text']
                
                # Parse JSON from LLM response
                json_start = llm_response.find('{')
                json_end = llm_response.rfind('}') + 1
                if json_start != -1 and json_end != -1:
                    json_str = llm_response[json_start:json_end]
                    llm_evaluation = json.loads(json_str)
                    
                    # Validate required fields
                    required_fields = ['overall_relevance_score', 'key_differences', 'examiner_notes']
                    
                    if all(field in llm_evaluation for field in required_fields):
                        print(f"✅ LLM evaluation for patent {patent_id}: Score={llm_evaluation['overall_relevance_score']}")
                        return llm_evaluation
                    else:
                        print(f"LLM response missing required fields (attempt {attempt + 1}/{max_retries})")
                        if attempt == max_retries - 1:
                            # Fallback to rule-based scoring
                            return calculate_fallback_relevance_score(patent_data, invention_context)
                else:
                    print(f"Could not find JSON in LLM response (attempt {attempt + 1}/{max_retries})")
                    if attempt == max_retries - 1:
                        return calculate_fallback_relevance_score(patent_data, invention_context)
                        
            except json.JSONDecodeError as je:
                print(f"JSON parsing error (attempt {attempt + 1}/{max_retries}): {je}")
                if attempt == max_retries - 1:
                    return calculate_fallback_relevance_score(patent_data, invention_context)
                    
            except Exception as e:
                print(f"LLM call error (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt == max_retries - 1:
                    return calculate_fallback_relevance_score(patent_data, invention_context)
            
            # Wait before retry
            if attempt < max_retries - 1:
                time.sleep(1)
        
        # Should not reach here, but fallback just in case
        return calculate_fallback_relevance_score(patent_data, invention_context)
        
    except Exception as e:
        print(f"Error in LLM patent relevance evaluation: {str(e)}")
        return calculate_fallback_relevance_score(patent_data, invention_context)

def calculate_fallback_relevance_score(patent_data: Dict, invention_context: Dict) -> Dict[str, Any]:
    """Simple fallback relevance scoring when LLM fails."""
    try:
        # Combine patent text fields for matching
        patent_text_parts = []
        
        title = patent_data.get('patent_title', '')
        if title:
            patent_text_parts.append(title)
        
        abstract = patent_data.get('patent_abstract', '')
        if abstract:
            patent_text_parts.append(abstract)
        
        patent_text = ' '.join(patent_text_parts).lower()
        
        # Get keywords
        keywords_string = invention_context.get('keywords', '')
        if not keywords_string:
            return {
                'overall_relevance_score': 0.0,
                'key_differences': [],
                'examiner_notes': 'Fallback scoring - no keywords available'
            }
        
        keyword_list = [k.strip().lower() for k in keywords_string.split(',') if k.strip()]
        if not keyword_list:
            return {
                'overall_relevance_score': 0.0,
                'key_differences': [],
                'examiner_notes': 'Fallback scoring - no valid keywords'
            }
        
        # Count matches
        matches = sum(1 for keyword in keyword_list if keyword in patent_text)
        base_score = matches / len(keyword_list)
        
        # Simple bonus for title/abstract matches
        title_lower = title.lower()
        title_matches = sum(1 for keyword in keyword_list if keyword in title_lower)
        if title_matches > 0:
            base_score += (title_matches / len(keyword_list)) * 0.3
        
        # Citation bonus
        citation_count = patent_data.get('citation_count', 0)
        if citation_count > 50:
            base_score += 0.1
        
        final_score = round(min(base_score, 1.0), 3)
        
        return {
            'overall_relevance_score': final_score,
            'key_differences': [],
            'examiner_notes': f'Fallback rule-based scoring: {matches}/{len(keyword_list)} keywords matched'
        }
        
    except Exception as e:
        print(f"Fallback scoring error: {e}")
        return {
            'overall_relevance_score': 0.0,
            'key_differences': [],
            'examiner_notes': f'Fallback scoring failed: {str(e)}'
        }

@tool
def store_patentview_analysis(pdf_filename: str, patent_data: Dict[str, Any]) -> str:
    """Store comprehensive PatentView patent analysis result with LLM evaluation in DynamoDB."""
    try:
        # Use patent_id as sort key
        sort_key = patent_data.get('patent_id') or patent_data.get('patent_number', 'unknown')
        
        # CRITICAL VALIDATION: Ensure patent has been evaluated by LLM
        llm_evaluation = patent_data.get('llm_evaluation', {})
        overall_relevance = llm_evaluation.get('overall_relevance_score', patent_data.get('relevance_score', 0.0))
        
        if overall_relevance == 0.000 and not llm_evaluation:
            return f"❌ REJECTED: Patent {sort_key} has not been evaluated by LLM. relevance_score=0, no llm_evaluation data. Must evaluate before storing."
        
        dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
        table = dynamodb.Table(RESULTS_TABLE)
        
        timestamp = datetime.utcnow().isoformat()
        
        # Helper function to handle empty values
        def get_value_or_na(value):
            return value if value else "N/A"
        
        # Extract inventor names from nested structure
        inventors = patent_data.get('inventors', [])
        inventor_names = []
        for inv in inventors:
            first = inv.get('inventor_name_first', '')
            last = inv.get('inventor_name_last', '')
            if first or last:
                full_name = f"{first} {last}".strip()
                inventor_names.append(full_name)
        inventors_str = '; '.join(inventor_names) if inventor_names else "N/A"
        
        # Extract assignee names from nested structure
        assignees = patent_data.get('assignees', [])
        assignee_names = []
        for asg in assignees:
            org = asg.get('assignee_organization', '')
            if org:
                assignee_names.append(org)
            else:
                first = asg.get('assignee_individual_name_first', '')
                last = asg.get('assignee_individual_name_last', '')
                if first or last:
                    full_name = f"{first} {last}".strip()
                    assignee_names.append(full_name)
        assignees_str = '; '.join(assignee_names) if assignee_names else "N/A"
        
        # Extract LLM evaluation data
        key_differences = llm_evaluation.get('key_differences', [])
        examiner_notes = llm_evaluation.get('examiner_notes', '')
        
        item = {
            # Primary Keys
            'pdf_filename': pdf_filename,
            'patent_number': sort_key,
            
            # Core Identity
            'patent_title': get_value_or_na(patent_data.get('patent_title', '')),
            'patent_abstract': get_value_or_na(patent_data.get('patent_abstract', '')),
            
            # Legal Status & Dates (Critical for novelty)
            'grant_date': get_value_or_na(patent_data.get('patent_date', '')),
            'filing_date': get_value_or_na(patent_data.get('patent_date', '')),
            'publication_date': get_value_or_na(patent_data.get('patent_date', '')),
            
            # Ownership
            'patent_inventors': inventors_str,
            'patent_assignees': assignees_str,
            
            # Citation Information (Important for novelty assessment)
            'forward_citations': patent_data.get('patent_num_times_cited_by_us_patents', 0),  # How many patents cite THIS one
            'backward_citations': patent_data.get('patent_num_us_patents_cited', 0),  # How many patents THIS one cites
            'foreign_citations': patent_data.get('patent_num_foreign_documents_cited', 0),  # Foreign documents cited
            'citation_count': patent_data.get('citation_count', 0),  # Legacy field (same as forward_citations)
            
            # LLM-Powered Relevance Assessment
            'relevance_score': Decimal(str(overall_relevance)),
            'key_differences': ', '.join(key_differences) if key_differences else 'None identified',
            'llm_examiner_notes': examiner_notes,
            
            # Search Metadata
            'search_timestamp': timestamp,
            'matching_keywords': get_value_or_na(patent_data.get('matching_keywords', '')),
            
            # PatentView URLs for reference
            'google_patents_url': f"https://patents.google.com/patent/US{sort_key}",
            
            # Legacy compatibility fields
            'publication_number': get_value_or_na(sort_key)
        }
        
        # Put item in DynamoDB
        table.put_item(Item=item)
        
        patent_title = patent_data.get('patent_title', 'Unknown Title')
        return f"Successfully stored PatentView patent {sort_key}: {patent_title} (Relevance: {overall_relevance}, Threat: {novelty_threat})"
        
    except Exception as e:
        sort_key = patent_data.get('patent_id') or patent_data.get('patent_number', 'unknown')
        return f"Error storing PatentView patent {sort_key}: {str(e)}"


# =============================================================================
# SEMANTIC SCHOLAR SEARCH TOOLS
# =============================================================================

def run_semantic_scholar_search_clean(search_query: str, limit: int = 30):
    """Run clean Semantic Scholar search with rate limiting (1 request per second)."""
    try:
        time.sleep(1.5)  # Slightly more conservative for refinement scenarios  
        response = requests.post( SEMANTIC_SCHOLAR_TOKEN_URL, data=f"grant_type=client_credentials&client_id={SEMANTIC_SCHOLAR_CLIENT_ID}&client_secret={SEMANTIC_SCHOLAR_CLIENT_SECRET}", headers={'Content-Type': 'application/x-www-form-urlencoded'}, timeout=30 )
        
        if response.status_code != 200:
            raise Exception(f"Semantic Scholar token request failed: {response.status_code} - {response.text}")
        
        token_data = response.json()
        access_token = token_data.get('access_token')
        
        if not access_token:
            raise Exception(f"No access token in Semantic Scholar response: {token_data}")
        mcp_client = MCPClient(lambda: create_streamable_http_transport(SEMANTIC_SCHOLAR_GATEWAY_URL, access_token))
        
        with mcp_client:
            tools = get_full_tools_list(mcp_client)
            if tools:
                print(f"DEBUG: Available Semantic Scholar tools: {[tool.tool_name for tool in tools]}")
                for i, tool in enumerate(tools):
                    print(f"  Tool {i+1}: {tool.tool_name} - {getattr(tool, 'description', 'No description')}")
            else:
                print("DEBUG: No tools found from MCP client")
            
            # Find the Semantic Scholar search tool
            if tools:
                semantic_scholar_tool = None
                for tool in tools:
                    if 'semantic' in tool.tool_name.lower() or 'searchScholarlyPapers' in tool.tool_name:
                        semantic_scholar_tool = tool
                        break
                
                # Use Semantic Scholar tool 
                tool_name = semantic_scholar_tool.tool_name if semantic_scholar_tool else tools[0].tool_name
                
                # Build clean arguments - only query, limit, and essential fields
                arguments = {
                    "query": search_query,
                    "limit": limit,
                    "fields": "title,abstract,authors,venue,year,citationCount,url,fieldsOfStudy,publicationTypes,openAccessPdf,referenceCount"
                }
                print(f"Clean search arguments: {arguments}")
                # Call tool
                result = mcp_client.call_tool_sync(
                    name=tool_name,
                    arguments=arguments,
                    tool_use_id=f"semantic-scholar-clean-{hash(search_query)}"
                )
                return result
            else:
                return None
                
    except Exception as e:
        print(f"Error in clean Semantic Scholar search: {e}")
        return None

@tool
def search_semantic_scholar_articles_strategic(keywords_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Execute intelligent LLM-driven scholarly article search for patent novelty assessment."""
    try:
        if not SEMANTIC_SCHOLAR_GATEWAY_URL:
            print("SEMANTIC_SCHOLAR_GATEWAY_URL not configured")
            return []

        # Extract invention context
        title = keywords_data.get('title', '')
        tech_description = keywords_data.get('technology_description', '')
        tech_applications = keywords_data.get('technology_applications', '')
        keywords_string = keywords_data.get('keywords', '')
        
        if not keywords_string:
            print("No keywords provided for search query generation")
            return []
        
        # Create LLM prompt for query generation
        query_generation_prompt = f"""You are a scholarly article search expert. Analyze this invention and generate optimal Semantic Scholar search queries.

        INVENTION CONTEXT:
        Title: {title}
        Technology Description: {tech_description}
        Applications: {tech_applications}
        Keywords: {keywords_string}

        SEMANTIC SCHOLAR QUERY SYNTAX:
        - Plain-text search: "pancreaticobiliary stent" (space-separated terms)
        - Multi-word phrases: "stent deployment mechanism" (all terms searched together)
        - Single keywords: "polyethylene" or "biliary"
        - Technical terms: "threaded stent" or "spiral deployment"
        - Avoid hyphens: use "machine learning" not "machine-learning" (hyphens yield no matches)
        - Note: No special operators (AND, OR, NOT, wildcards) are supported - use plain text only

        TASK: Generate 5 strategic search queries that will find relevant academic papers for patent novelty assessment.

        Consider:
        1. Single high-impact keywords vs multi-word combinations
        2. Technical device terms vs medical application terms
        3. Broad searches vs specific mechanism searches
        4. Problem-focused vs solution-focused queries

        RESPOND IN THIS EXACT JSON FORMAT:
        [
            {{
                "query": "pancreaticobiliary stent",
                "rationale": "Direct search for the main medical device type"
            }},
            {{
                "query": "biliary stricture treatment",
                "rationale": "Search for the medical problem being addressed"
            }},
            {{
                "query": "threaded stent deployment",
                "rationale": "Focus on the specific deployment mechanism"
            }}
        ]
        Generate 3-5 queries that cover different aspects of the invention for comprehensive prior art discovery."""

        # Generate search queries (LLM + fallback)
        search_queries = []
        
        try:
            bedrock_client = boto3.client('bedrock-runtime', region_name=AWS_REGION)
            # Prepare the request for Claude
            request_body = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 2000,
                "messages": [
                    {
                        "role": "user",
                        "content": query_generation_prompt
                    }
                ]
            }
            
            # Make the LLM call
            response = bedrock_client.invoke_model(
                modelId="us.anthropic.claude-3-7-sonnet-20250219-v1:0",
                body=json.dumps(request_body)
            )
            
            # Parse the response
            response_body = json.loads(response['body'].read())
            llm_response = response_body['content'][0]['text']
            print(f"LLM Response: {llm_response[:200]}...")
            
            # Parse JSON from LLM response
            try:
                # Extract JSON from the response (it might have extra text)
                json_start = llm_response.find('[')
                json_end = llm_response.rfind(']') + 1
                if json_start != -1 and json_end != -1:
                    json_str = llm_response[json_start:json_end]
                    search_queries = json.loads(json_str)
                    print(f"Successfully parsed {len(search_queries)} queries from LLM")
                else:
                    print("Could not find JSON in LLM response")

            except json.JSONDecodeError as je:
                print(f"Failed to parse LLM JSON response: {je}")
                
        except Exception as e:
            print(f"LLM call failed: {e}")
        
        # Fallback: Generate queries from keywords if LLM failed
        if not search_queries:
            print("Using fallback keyword-based query generation...")
            keyword_list = [k.strip() for k in keywords_string.split(',') if k.strip()]
            num_keywords = len(keyword_list)
            
            # Individual searches (adaptive count)
            if num_keywords <= 5:
                for kw in keyword_list:
                    search_queries.append({"query": kw, "rationale": f"Direct search for: {kw}"})
            elif num_keywords <= 10:
                for kw in keyword_list[:5]:
                    search_queries.append({"query": kw, "rationale": f"Direct search for: {kw}"})
            else:
                for kw in keyword_list[:6]:
                    search_queries.append({"query": kw, "rationale": f"Direct search for: {kw}"})
            
            # Smart combinations
            if num_keywords >= 2:
                search_queries.append({
                    "query": f"{keyword_list[0]} {keyword_list[1]}",
                    "rationale": f"Combined search: {keyword_list[0]} {keyword_list[1]}"
                })
                
                if num_keywords >= 3:
                    search_queries.append({
                        "query": f"{keyword_list[1]} {keyword_list[2]}",
                        "rationale": f"Combined search: {keyword_list[1]} {keyword_list[2]}"
                    })
                
                if num_keywords > 10:
                    search_queries.append({
                        "query": f"{keyword_list[3]} {keyword_list[7] if len(keyword_list) > 7 else keyword_list[-1]}",
                        "rationale": f"Diverse combination search"
                    })
            
            # Limit to 8 queries max
            search_queries = search_queries[:8]
        
        if not search_queries:
            print("No search queries generated")
            return []
        
        print(f"Generated {len(search_queries)} strategic search queries")
        for i, query in enumerate(search_queries, 1):
            print(f"  {i}. '{query['query']}' - {query['rationale']}")
        
        # PHASE 2: Execute adaptive search with refinement
        print("Phase 2: Executing adaptive searches...")
        all_relevant_papers = []
        
        for query_info in search_queries:
            query_refinement_attempts = 0
            max_query_refinements = 3  # Per query limit
            print(f"Executing search: '{query_info['query']}'")
            
            # Execute initial search with rate limiting
            result = run_semantic_scholar_search_clean(
                search_query=query_info['query'],
                limit=20  # Reduced limit to manage rate limiting
            )
            
            if result and isinstance(result, dict) and 'content' in result:
                content = result['content']
                if isinstance(content, list) and len(content) > 0:
                    text_content = content[0].get('text', '') if isinstance(content[0], dict) else str(content[0])
                    
                    try:
                        data = json.loads(text_content)
                        articles = data.get("data", [])
                        total_results = data.get("total", 0)
                        
                        print(f"Query '{query_info['query']}': Found {len(articles)} papers (total: {total_results})")
                        
                        # Quality assessment with refinement enabled
                        quality_assessment = assess_search_result_quality(articles, total_results, query_info, keywords_data)
                        print(f"Quality assessment: {quality_assessment['reason']}")

                        if quality_assessment['action'] == 'refine' and query_refinement_attempts < max_query_refinements:
                            print(f"Refining query (attempt {query_refinement_attempts + 1}/{max_query_refinements})")
                            
                            # Generate refined query
                            refined_query = generate_refined_query(query_info, quality_assessment, keywords_data)
                            print(f"Original query: '{query_info['query']}'")
                            
                            # Check if refinement failed
                            if refined_query == "REFINEMENT_FAILED":
                                print("LLM refinement failed, proceeding with original results")
                                current_articles = articles
                                query_refinement_attempts += 1  # Count as attempt
                            else:
                                print(f"Refined query: '{refined_query}'")
                                refined_result = run_semantic_scholar_search_clean(
                                    search_query=refined_query,
                                    limit=20
                                )
                                
                                if refined_result and isinstance(refined_result, dict) and 'content' in refined_result:
                                    refined_content = refined_result['content']
                                    if isinstance(refined_content, list) and len(refined_content) > 0:
                                        refined_text_content = refined_content[0].get('text', '') if isinstance(refined_content[0], dict) else str(refined_content[0])
                                        
                                        try:
                                            refined_data = json.loads(refined_text_content)
                                            refined_articles = refined_data.get("data", [])
                                            refined_total = refined_data.get("total", 0)
                                            
                                            print(f"Refined query '{refined_query}': Found {len(refined_articles)} papers (total: {refined_total})")
                                            
                                            # Use refined results if they're better
                                            if len(refined_articles) > len(articles) or refined_total < total_results:
                                                current_articles = refined_articles
                                                query_info['query'] = refined_query  # Update for tracking
                                                print("Using refined results")
                                            else:
                                                current_articles = articles
                                                print("Keeping original results (refinement didn't improve)")
                                                
                                            query_refinement_attempts += 1
                                            
                                        except json.JSONDecodeError:
                                            print("Failed to parse refined search results, using original")
                                            current_articles = articles
                                    else:
                                        print("No content in refined results, using original")
                                        current_articles = articles
                                else:
                                    print("Refined search failed, using original results")
                                    current_articles = articles
                        else:
                            current_articles = articles
                            if quality_assessment['action'] == 'refine':
                                print(f"Max refinements ({max_query_refinements}) reached, proceeding with current results")
                        
                        # Track refinement statistics
                        if query_refinement_attempts > 0:
                            print(f"Refinement summary for '{query_info['query']}': {query_refinement_attempts} attempts made")
                        
                        # Evaluate each paper for relevance using LLM
                        for article in current_articles:
                            processed_article = {
                                'paperId': article.get('paperId', 'unknown'),
                                'title': article.get('title', 'Unknown Title'),
                                'authors': extract_semantic_scholar_authors(article.get('authors', [])),
                                'venue': article.get('venue', 'Unknown Venue'),
                                'published_date': extract_semantic_scholar_published_date(article),
                                'abstract': article.get('abstract', ''),
                                'url': article.get('url', ''),
                                'citation_count': article.get('citationCount', 0),
                                'reference_count': article.get('referenceCount', 0),
                                'fields_of_study': article.get('fieldsOfStudy', []),
                                'publication_types': article.get('publicationTypes', []),
                                'open_access_pdf': extract_open_access_pdf(article.get('openAccessPdf')),
                                'search_query_used': query_info['query'],
                                'matching_keywords': query_info['query']
                            }
                            
                            # LLM-powered relevance evaluation
                            relevance_assessment = evaluate_paper_relevance_with_llm_internal(processed_article, keywords_data)
                            
                            # Add LLM assessment to article data
                            processed_article['llm_decision'] = relevance_assessment['decision']
                            processed_article['llm_reasoning'] = relevance_assessment['reasoning']
                            processed_article['technical_overlaps'] = relevance_assessment['technical_overlaps']
                            processed_article['novelty_impact_assessment'] = relevance_assessment['novelty_impact']
                            
                            # Keep only papers that LLM determines are relevant
                            if relevance_assessment['decision'] == 'KEEP':
                                all_relevant_papers.append(processed_article)
                                print(f"KEPT: {processed_article['title'][:60]}...")
                                print(f"Reason: {relevance_assessment['reasoning'][:100]}...")
                            else:
                                print(f"DISCARDED: {processed_article['title'][:60]}...")
                                print(f"Reason: {relevance_assessment['reasoning'][:100]}...")
                                
                    except json.JSONDecodeError as je:
                        print(f"JSON decode error for query '{query_info['query']}': {je}")
                else:
                    print(f"No content in result for query '{query_info['query']}'")
            else:
                print(f"No result for query '{query_info['query']}'")
        
        # Remove duplicates and select top 6 papers
        unique_papers = {}
        for paper in all_relevant_papers:
            paper_id = paper['paperId']
            if paper_id not in unique_papers:
                unique_papers[paper_id] = paper
        
        # Sort by citation count and relevance, take top 6
        final_papers = sorted(unique_papers.values(), key=lambda x: x['citation_count'], reverse=True)[:6]
        
        print(f"Final selection: {len(final_papers)} highly relevant papers for patent novelty assessment")
        for i, paper in enumerate(final_papers, 1):
            print(f"{i}. {paper['title'][:70]}... (Citations: {paper['citation_count']})")
            print(f"Impact: {paper['novelty_impact_assessment']}")
            print()
        return final_papers
        
    except Exception as e:
        print(f"Error in strategic Semantic Scholar search: {e}")
        import traceback
        traceback.print_exc()
        return []

def extract_semantic_scholar_authors(authors_list: List[Dict]) -> str:
    """Extract author names from Semantic Scholar author list."""
    try:
        author_names = []
        for author in authors_list[:5]:  # Limit to first 5 authors
            name = author.get('name', '')
            if name:
                author_names.append(name)
        
        if len(authors_list) > 5:
            author_names.append("et al.")
        
        return '; '.join(author_names) if author_names else 'Unknown Authors'
    except Exception:
        return 'Unknown Authors'

def extract_semantic_scholar_published_date(article: Dict) -> str:
    """Extract published date from Semantic Scholar article."""
    try:
        # Try publicationDate first
        pub_date = article.get('publicationDate')
        if pub_date:
            return pub_date
        
        # Fallback to year
        year = article.get('year')
        if year:
            return str(year)
        
        return ''
    except Exception:
        return ''

def extract_open_access_pdf(open_access_info: Dict) -> str:
    """Extract open access PDF URL from Semantic Scholar response."""
    try:
        if open_access_info and isinstance(open_access_info, dict):
            return open_access_info.get('url', '')
        return ''
    except Exception:
        return ''

def assess_search_result_quality(articles: List[Dict], total_results: int, query_info: Dict, keywords_data: Dict) -> Dict[str, str]:
    """Assess the quality of search results and determine if refinement is needed."""
    try:
        # Quality assessment logic
        if total_results == 0:
            return {
                'action': 'refine',
                'reason': 'No results found - query may be too specific or use uncommon terms'
            }
        elif total_results > 10000:
            return {
                'action': 'refine', 
                'reason': 'Too many results - query is too broad, need more specific terms'
            }
        elif len(articles) < 5:
            return {
                'action': 'refine',
                'reason': 'Very few results returned - try broader or alternative terms'
            }
        else:
            # Check if articles have abstracts (important for relevance assessment)
            articles_with_abstracts = sum(1 for article in articles if article.get('abstract') and article.get('abstract').strip())
            if articles_with_abstracts < len(articles) * 0.3:  # Less than 30% have abstracts
                return {
                    'action': 'refine',
                    'reason': 'Most papers lack abstracts - try different query to get better quality papers'
                }
            else:
                return {
                    'action': 'proceed',
                    'reason': 'Good result quality - proceeding with relevance evaluation'
                }
                
    except Exception as e:
        print(f"Error assessing search quality: {e}")
        return {
            'action': 'proceed',
            'reason': 'Assessment failed - proceeding with current results'
        }

def generate_refined_query(original_query_info: Dict, quality_assessment: Dict, keywords_data: Dict) -> str:
    """Use LLM to intelligently refine search query based on quality issues."""
    try:
        # Extract context
        original_query = original_query_info['query']
        problem_reason = quality_assessment['reason']
        invention_title = keywords_data.get('title', '')
        keywords_string = keywords_data.get('keywords', '')
        
        # Create LLM refinement prompt
        refinement_prompt = f"""You are a scholarly article search expert. The previous search query had issues and needs refinement.

        INVENTION CONTEXT:
        Title: {invention_title}
        Available Keywords: {keywords_string}

        PREVIOUS QUERY PROBLEM:
        Original Query: "{original_query}"
        Issue: {problem_reason}

        TASK: Generate ONE improved search query that fixes this specific issue.

        REFINEMENT STRATEGIES:
        - If "no results" or "too specific": Make broader, use fewer/different terms
        - If "too many results" or "too broad": Make more specific, add constraining terms  
        - If "few results": Try alternative keywords or synonyms
        - If "lack abstracts": Use more academic/research-focused terms

        RESPOND WITH ONLY THE NEW QUERY (no explanation):"""

        # Call Claude to generate refined query
        bedrock_client = boto3.client('bedrock-runtime', region_name=AWS_REGION)
        request_body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 100,
            "messages": [{"role": "user", "content": refinement_prompt}]
        }
        response = bedrock_client.invoke_model(
            modelId="us.anthropic.claude-3-7-sonnet-20250219-v1:0",
            body=json.dumps(request_body)
        )
        response_body = json.loads(response['body'].read())
        refined_query = response_body['content'][0]['text'].strip()
        refined_query = refined_query.strip('"').strip("'")
        return refined_query
        
    except Exception as e:
        print(f"Error generating LLM-refined query: {e}")
        return "REFINEMENT_FAILED"  # Special marker

def evaluate_paper_relevance_with_llm_internal(paper_data: Dict, invention_context: Dict) -> Dict[str, str]:
    """Internal LLM evaluation function (not a tool)"""
    try:
        # Extract paper information
        paper_title = paper_data.get('title', 'Unknown Title')
        paper_abstract = paper_data.get('abstract', '')
        paper_authors = paper_data.get('authors', '')
        paper_venue = paper_data.get('venue', '')
        paper_year = paper_data.get('published_date', '')
        fields_of_study = paper_data.get('fields_of_study', [])
        
        # Extract invention context
        invention_title = invention_context.get('title', 'Unknown Invention')
        tech_description = invention_context.get('technology_description', '')
        tech_applications = invention_context.get('technology_applications', '')
        keywords = invention_context.get('keywords', '')
        
        # Skip papers without abstracts
        if not paper_abstract or len(paper_abstract.strip()) < 50:
            return {
                'decision': 'DISCARD',
                'reasoning': 'Paper lacks sufficient abstract content for meaningful relevance assessment',
                'technical_overlaps': [],
                'novelty_impact': 'Cannot assess - insufficient content'
            }
        
        # Make LLM call for relevance evaluation - MUST WORK
        evaluation_prompt = f"""You are a patent novelty assessment expert. Evaluate if this research paper is relevant for assessing the novelty of the given invention.

        INVENTION TO ASSESS:
        Title: {invention_title}
        Technical Description: {tech_description}
        Applications: {tech_applications}
        Key Technologies: {keywords}

        RESEARCH PAPER TO EVALUATE:
        Title: {paper_title}
        Abstract: {paper_abstract}
        Authors: {paper_authors}
        Venue: {paper_venue}
        Year: {paper_year}
        Fields: {', '.join(fields_of_study) if fields_of_study else 'Not specified'}

        ANALYSIS TASK:
        Determine if this paper could impact the novelty assessment of the invention by analyzing:
        1. TECHNICAL OVERLAP: Does the paper describe similar technologies, methods, or mechanisms?
        2. PROBLEM DOMAIN: Does it address the same or related problems?
        3. APPLICATION SIMILARITY: Does it target similar use cases or applications?
        4. PRIOR ART POTENTIAL: Could this work be considered prior art that affects novelty?

        RESPOND IN THIS EXACT JSON FORMAT:
        {{
            "decision": "KEEP" or "DISCARD",
            "reasoning": "Detailed 2-3 sentence explanation of why this paper is/isn't relevant for novelty assessment",
            "technical_overlaps": ["list", "of", "specific", "technical", "overlaps"],
            "novelty_impact": "Brief assessment of how this paper could affect the invention's novelty claims"
        }}

        Be precise and focus specifically on patent novelty implications."""

        # Make the LLM call with retry logic
        max_retries = 3
        for attempt in range(max_retries):
            try:
                bedrock_client = boto3.client('bedrock-runtime', region_name=AWS_REGION)
                # Prepare the request for Claude
                request_body = {
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 1000,
                    "messages": [
                        {
                            "role": "user",
                            "content": evaluation_prompt
                        }
                    ]
                }
                # Make the LLM call
                response = bedrock_client.invoke_model(
                    modelId="us.anthropic.claude-3-7-sonnet-20250219-v1:0",
                    body=json.dumps(request_body)
                )
                
                # Parse the response
                response_body = json.loads(response['body'].read())
                llm_response = response_body['content'][0]['text']
                
                # Try to parse JSON from LLM response
                json_start = llm_response.find('{')
                json_end = llm_response.rfind('}') + 1
                if json_start != -1 and json_end != -1:
                    json_str = llm_response[json_start:json_end]
                    llm_evaluation = json.loads(json_str)
                    
                    # Validate required fields
                    if 'decision' in llm_evaluation and 'reasoning' in llm_evaluation:
                        return {
                            'decision': llm_evaluation.get('decision', 'DISCARD'),
                            'reasoning': llm_evaluation.get('reasoning', 'LLM evaluation completed'),
                            'technical_overlaps': llm_evaluation.get('technical_overlaps', []),
                            'novelty_impact': llm_evaluation.get('novelty_impact', 'Impact assessment completed')
                        }
                    else:
                        print(f"LLM response missing required fields (attempt {attempt + 1}/{max_retries})")
                        if attempt == max_retries - 1:
                            return {
                                'decision': 'DISCARD',
                                'reasoning': 'LLM response validation failed - missing required fields after all retries',
                                'technical_overlaps': [],
                                'novelty_impact': 'Unable to assess due to LLM validation error'
                            }
                else:
                    print(f"Could not find JSON in LLM response (attempt {attempt + 1}/{max_retries})")
                    if attempt == max_retries - 1:
                        return {
                            'decision': 'DISCARD',
                            'reasoning': 'LLM response parsing failed - could not extract JSON after all retries',
                            'technical_overlaps': [],
                            'novelty_impact': 'Unable to assess due to LLM parsing error'
                        }
                        
            except json.JSONDecodeError as je:
                print(f"JSON parsing error (attempt {attempt + 1}/{max_retries}): {je}")
                if attempt == max_retries - 1:
                    return {
                        'decision': 'DISCARD',
                        'reasoning': f'LLM JSON parsing failed after all retries: {str(je)}',
                        'technical_overlaps': [],
                        'novelty_impact': 'Unable to assess due to JSON parsing error'
                    }
                    
            except Exception as e:
                print(f"LLM call error (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt == max_retries - 1:
                    return {
                        'decision': 'DISCARD',
                        'reasoning': f'LLM evaluation failed after all retries: {str(e)}',
                        'technical_overlaps': [],
                        'novelty_impact': 'Unable to assess due to LLM failure'
                    }
            
            # Wait before retry
            if attempt < max_retries - 1:
                time.sleep(1)  # Wait 1 second before retry
        
    except Exception as e:
        print(f"Error in LLM paper relevance evaluation: {str(e)}")
        return {
            'decision': 'DISCARD',
            'reasoning': f'Evaluation failed due to error: {str(e)}',
            'technical_overlaps': [],
            'novelty_impact': 'Unable to assess due to evaluation error'
        }

@tool
def store_semantic_scholar_analysis(pdf_filename: str, article_data: Dict[str, Any]) -> str:
    """Store LLM-analyzed Semantic Scholar article in DynamoDB with enhanced metadata."""
    try:
        dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
        table = dynamodb.Table(ARTICLES_TABLE)
        timestamp = datetime.utcnow().isoformat()
        paper_id = article_data.get('paperId', 'unknown')
        article_title = article_data.get('title', 'Unknown Title')

        # Use paperId as the sort key
        item = {
            'pdf_filename': pdf_filename,
            'article_doi': paper_id,
            'article_title': article_title,
            'authors': article_data.get('authors', 'Unknown Authors'),
            'journal': article_data.get('venue', 'Unknown Venue'),
            'published_date': article_data.get('published_date', ''),
            'search_timestamp': timestamp,
            'article_url': article_data.get('url', ''),
            'citation_count': article_data.get('citation_count', 0),
            'article_type': ', '.join(article_data.get('publication_types', [])) if article_data.get('publication_types') else 'Unknown',
            'fields_of_study': ', '.join(article_data.get('fields_of_study', [])) if article_data.get('fields_of_study') else '',
            'open_access_pdf_url': article_data.get('open_access_pdf', ''),
            'search_query_used': article_data.get('search_query_used', ''),
            'abstract': article_data.get('abstract', ''),
            
            # Updated LLM Analysis Results (using new structure)
            'llm_decision': article_data.get('llm_decision', 'UNKNOWN'),
            'llm_reasoning': article_data.get('llm_reasoning', ''),
            'key_technical_overlaps': ', '.join(article_data.get('technical_overlaps', [])) if article_data.get('technical_overlaps') else '',
            'novelty_impact_assessment': article_data.get('novelty_impact_assessment', ''),
            
            # Legacy compatibility - set relevance score based on decision
            'relevance_score': Decimal('0.8') if article_data.get('llm_decision') == 'KEEP' else Decimal('0.2'),
            'matching_keywords': article_data.get('search_query_used', ''),
        }
        table.put_item(Item=item)
        return f"Successfully stored LLM-analyzed article {paper_id}: {article_title} (Decision: {article_data.get('llm_decision', 'UNKNOWN')})"
        
    except Exception as e:
        return f"Error storing Semantic Scholar article {article_data.get('paperId', 'unknown')}: {str(e)}"

# =============================================================================
# AGENT DEFINITIONS
# =============================================================================

# Keyword Generator Agent
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
    - Focus on SINGLE WORDS (not sentences or phrases)
    - Include technical terminology that appears in patent databases
    - Extract both specific terms ("polyethylene") and general terms ("plastic")
    - Include process terms ("deployment", "rotation", "threading")
    - Add application domain terms ("biliary", "pancreatic", "endoscopic")
    - Include synonyms and variations patent searchers would use
    - Aim for 12-15 high-impact keywords MAXIMUM - quality over quantity
    - Each keyword must be highly relevant and likely to appear in prior art

    OUTPUT FORMAT (use this exact structure):
    # Patent Analysis

    ## Title
    [Create a concise, professional title for the invention]

    ## Technology Description
    [Write a brief technical description of what the invention is in 100-150 words - focus on the core technology/mechanism]

    ## Technology Applications
    [Write a brief description of what problems it solves and where it's used in 100-150 words]

    ## Keywords
    [List 12-15 comma-separated keywords MAXIMUM that capture the invention's essence - mix of single words and 2-3 word phrases. Focus on the MOST important terms only.]

    QUALITY STANDARD: Your keywords should match the quality of professional patent searchers. Each keyword should be a term that could realistically appear in a competing patent or prior art document.

    After completing your analysis, ALWAYS use the store_keywords_in_dynamodb tool to save all four fields (title, technology_description, technology_applications, keywords)."""
)

# PatentView Search Agent - Keyword-Based Direct Search
patentview_search_agent = Agent(
    model="us.anthropic.claude-3-7-sonnet-20250219-v1:0",
    tools=[read_keywords_from_dynamodb, search_all_keywords_and_prefilter, evaluate_patent_relevance_llm, store_patentview_analysis],
    system_prompt="""You are an AI Patent Search Expert conducting comprehensive prior art searches using direct keyword-based queries.

    MISSION: Conduct comprehensive prior art searches using direct keyword-based queries for maximum coverage and efficiency.

    WORKFLOW - SIMPLIFIED 4-STEP PROCESS:

    1. READ KEYWORDS:
    - Call: read_keywords_from_dynamodb(pdf_filename)
    - Extract the keywords string from the result

    2. SEARCH ALL KEYWORDS (ONE TOOL CALL):
    - Call: search_all_keywords_and_prefilter(keywords_string, top_n=20)
    - This automatically:
        * Parses all keywords (detects multi-word phrases)
        * Searches each keyword (top 10 newest per keyword)
        * Deduplicates by patent_id
        * Pre-filters to top 20 by citation_count
    - Returns: 20 patents ready for evaluation

    3. EVALUATE EACH PATENT:
    - For EACH of the 20 patents returned:
    - Call: evaluate_patent_relevance_llm(patent, keywords_data)
    - Attach the evaluation to the patent object

    4. STORE TOP 8:
    - Sort patents by relevance_score (descending)
    - For the top 8 patents:
    - Call: store_patentview_analysis(pdf_filename, patent)

    EXAMPLE WORKFLOW:
    ```python
    # Step 1: Get keywords
    keywords_data = read_keywords_from_dynamodb(pdf_filename)
    keywords_string = keywords_data['keywords']

    # Step 2: Search all keywords in ONE call
    search_result = search_all_keywords_and_prefilter(keywords_string, top_n=20)
    top_20_patents = search_result['patents']

    # Step 3: Evaluate each patent
    for patent in top_20_patents:
        llm_eval = evaluate_patent_relevance_llm(patent, keywords_data)
        patent['llm_evaluation'] = llm_eval
        patent['relevance_score'] = llm_eval['overall_relevance_score']

    # Step 4: Store top 8
    top_8 = sorted(top_20_patents, key=lambda x: x['relevance_score'], reverse=True)[:8]
    for patent in top_8:
        store_patentview_analysis(pdf_filename, patent)
    ```

    QUALITY STANDARDS:
    - Direct keyword search ensures comprehensive coverage
    - Top 10 newest patents per keyword captures recent prior art
    - Pre-filtering by citations focuses on most impactful patents
    - LLM evaluation provides deep semantic relevance assessment
    - Top 8 storage ensures best prior art is preserved

    CRITICAL RULES:
    - Use search_all_keywords_and_prefilter() for ALL keyword searching (ONE call)
    - This tool handles parsing, searching, deduplication, and pre-filtering automatically
    - Evaluate ALL 20 returned patents with evaluate_patent_relevance_llm()
    - Store EXACTLY the top 8 highest-scoring patents (sorted by relevance_score descending)
    - Store ALL 8 patents regardless of their absolute score values (even if scores are 0.2, 0.3, etc.)
    - The top 8 patents by score are ALWAYS stored - no minimum score threshold
    - NEVER store patents without LLM evaluation - but once evaluated, store top 8 regardless of score"""
)

# Scholarly Article Search Agent (Semantic Scholar Only)
scholarly_article_agent = Agent(
    model="us.anthropic.claude-3-7-sonnet-20250219-v1:0",
    tools=[read_keywords_from_dynamodb, search_semantic_scholar_articles_strategic, 
           store_semantic_scholar_analysis],
    system_prompt="""You are an Intelligent Scholarly Article Search Expert using LLM-driven adaptive search for Patent Novelty Assessment.

    EXECUTE THIS WORKFLOW EXACTLY:

    1. READ INVENTION CONTEXT
    - Use read_keywords_from_dynamodb to get complete invention data
    - Extract title, technology description, applications, and keywords

    2. EXECUTE INTELLIGENT SEARCH
    - Use search_semantic_scholar_articles_strategic with the full invention context
    - This tool will automatically:
      * Generate optimal search queries using LLM analysis
      * Execute adaptive searches with refinement based on result quality
      * Evaluate each paper using LLM for semantic relevance
      * Return only the top 6 most relevant papers

    3. STORE RESULTS
    - For each paper returned by the strategic search, use store_semantic_scholar_analysis
    - Pass the complete paper data object which includes LLM analysis results

    CRITICAL PRINCIPLES:
    - Trust the LLM-driven search strategy - it will handle query generation and refinement
    - Focus on semantic relevance, not just keyword matching
    - Each paper has been pre-evaluated by LLM for relevance to patent novelty
    - Store all papers returned by the strategic search (they are already filtered)
    - Target exactly 6 highly relevant papers for comprehensive novelty assessment

    QUALITY ASSURANCE:
    - The strategic search uses adaptive refinement based on result quality
    - LLM evaluates each paper's abstract for technical overlap and novelty impact
    - Only papers with proven relevance are returned
    - Detailed reasoning and technical overlaps are captured for transparency

    Your goal: Execute the intelligent search workflow to identify 6 semantically relevant academic papers that could meaningfully impact patent novelty assessment, with full LLM reasoning for each selection."""
)

# =============================================================================
# ORCHESTRATOR LOGIC
# =============================================================================

async def handle_keyword_generation(payload):
    """Handle keyword generation requests."""
    print("🔍 Orchestrator: Routing to Keyword Generator Agent")
    
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            payload = {"prompt": payload}
    
    prompt = payload.get("prompt")
    bda_file_path = payload.get("bda_file_path")
    
    if not prompt:
        yield {"error": "Error: 'prompt' is required for keyword generation."}
        return
    
    # Extract PDF filename from BDA file path
    pdf_filename = "unknown"
    if bda_file_path:
        path_parts = bda_file_path.split('/')
        if len(path_parts) > 2:
            filename_timestamp = path_parts[2] 
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
            elif "output" in event:
                # Handle output events from Strands agent
                full_response += str(event["output"])
            elif "current_tool_use" in event and event["current_tool_use"].get("name"):
                yield {"tool_name": event["current_tool_use"]["name"], "agent": "keyword_generator"}
            elif "error" in event:
                yield {"error": event["error"]}
                return
            elif "content" in event:
                # Handle content events
                full_response += str(event["content"])
        
        # Yield the complete response once streaming is done
        if full_response.strip():
            yield {"response": full_response, "agent": "keyword_generator"}
        else:
            yield {"error": "No response generated from keyword generator agent"}
                
    except Exception as e:
        print(f"Keyword generation error: {str(e)}")
        print(f"Error type: {type(e)}")
        import traceback
        traceback.print_exc()
        yield {"error": f"Error in keyword generation: {str(e)}"}

async def handle_patentview_search(payload):
    """Handle PatentView patent search requests."""
    print("🔍 Orchestrator: Routing to PatentView Search Agent")
    
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            payload = {"pdf_filename": payload}
    
    pdf_filename = payload.get("pdf_filename")
    
    if not pdf_filename:
        yield {"error": "Error: 'pdf_filename' is required for PatentView search."}
        return
    
    enhanced_prompt = f"""Search for patents similar to the invention in PDF: {pdf_filename}

    INSTRUCTIONS:
    1. Read keywords from DynamoDB for this PDF
    2. Analyze the invention's technical aspects
    3. Execute multiple strategic PatentView searches via Gateway
    4. Score and rank results by relevance using PatentView data
    5. Select top 6 most relevant patents
    6. Store results with comprehensive metadata including abstracts

    Focus on granted patents that could impact novelty assessment using PatentView's rich database."""
    
    try:
        full_response = ""
        search_metadata = {"strategies_used": [], "total_results": 0}
        
        async for event in patentview_search_agent.stream_async(enhanced_prompt):
            if "data" in event:
                full_response += event["data"]
            elif "current_tool_use" in event and event["current_tool_use"].get("name"):
                tool_name = event["current_tool_use"]["name"]
                yield {"tool_name": tool_name, "agent": "patentview_search"}
                if tool_name in ["search_all_keywords_and_prefilter", "evaluate_patent_relevance_llm", "store_patentview_analysis"]:
                    search_metadata["strategies_used"].append(tool_name)
            elif "error" in event:
                yield {"error": event["error"]}
                return
        
        if full_response.strip():
            yield {"response": full_response, "search_metadata": search_metadata, "agent": "patentview_search"}
        else:
            yield {"response": "PatentView search completed successfully", "search_metadata": search_metadata, "agent": "patentview_search"}
                
    except KeyError as e:
        # Harmless KeyError at end of stream - agent finished successfully
        if str(e) == "'output'":
            print(f"Agent stream ended (harmless KeyError: {e})")
            yield {"response": "PatentView search completed successfully", "search_metadata": search_metadata, "agent": "patentview_search"}
        else:
            print(f"PatentView search KeyError: {str(e)}")
            import traceback
            traceback.print_exc()
            yield {"error": f"Error in PatentView search: {str(e)}"}
    except Exception as e:
        print(f"PatentView search error: {str(e)}")
        print(f"Error type: {type(e)}")
        import traceback
        traceback.print_exc()
        yield {"error": f"Error in PatentView search: {str(e)}"}

async def handle_scholarly_search(payload):
    """Handle scholarly article search requests using Semantic Scholar."""
    print("🔍 Orchestrator: Routing to Scholarly Article Search Agent (Semantic Scholar)")
    
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            payload = {"pdf_filename": payload}
    
    pdf_filename = payload.get("pdf_filename")
    
    if not pdf_filename:
        yield {"error": "Error: 'pdf_filename' is required for scholarly article search."}
        return
    
    enhanced_prompt = f"""Execute ADVANCED LLM-POWERED scholarly article search for patent novelty assessment of PDF: {pdf_filename}

    CRITICAL WORKFLOW:
    1. Read complete patent analysis data from DynamoDB (title, description, applications, keywords)
    2. Use search_semantic_scholar_articles_strategic with the FULL invention context
    3. The strategic search will automatically:
       - Execute 4-5 intelligent search strategies
       - Apply LLM analysis to each paper's abstract for semantic relevance
       - Keep only papers with LLM score ≥ 7 and decision = "KEEP"
       - Return top 8 semantically relevant papers with detailed LLM reasoning

    LLM-POWERED ANALYSIS:
    - Each paper's abstract is analyzed by LLM for semantic relevance to the invention
    - LLM considers technical overlap, problem domain similarity, and prior art potential
    - Only papers with proven semantic relevance are kept
    - Detailed reasoning and technical overlaps are captured

    STORAGE INSTRUCTIONS:
    - For each LLM-approved article, call: store_semantic_scholar_analysis(pdf_filename, article_data)
    - Pass the complete article data object which includes all LLM analysis results
    - All LLM reasoning, technical overlaps, and novelty impact assessments are automatically stored

    QUALITY ASSURANCE:
    - Focus on semantic understanding, not just keyword matching
    - Each stored paper has LLM-verified relevance for patent novelty assessment
    - Detailed explanations provide transparency in selection process
    - Target 5-8 highly relevant papers with proven technical overlap

    Your goal: Use LLM intelligence to identify truly relevant academic research that could meaningfully impact patent novelty assessment, with full reasoning and technical overlap analysis."""
        
    try:
        full_response = ""
        search_metadata = {"strategies_used": [], "total_results": 0}
        
        async for event in scholarly_article_agent.stream_async(enhanced_prompt):
            if "data" in event:
                full_response += event["data"]
            elif "current_tool_use" in event and event["current_tool_use"].get("name"):
                tool_name = event["current_tool_use"]["name"]
                yield {"tool_name": tool_name, "agent": "scholarly_search"}
                if tool_name == "search_semantic_scholar_articles":
                    search_metadata["strategies_used"].append(tool_name)
            elif "error" in event:
                yield {"error": event["error"]}
                return
        
        if full_response.strip():
            yield {"response": full_response, "search_metadata": search_metadata, "agent": "scholarly_search"}
        else:
            yield {"error": "No response generated from scholarly article search agent"}
                
    except Exception as e:
        yield {"error": f"Error in scholarly article search: {str(e)}"}

async def handle_orchestrator_request(payload):
    """Main orchestrator logic - routes requests to appropriate agents."""
    print(f"🎯 Orchestrator: Received payload: {json.dumps(payload, indent=2)}")
    
    # Determine action type from payload
    action = payload.get("action")
    
    # If no explicit action, try to infer from payload structure
    if not action:
        if payload.get("bda_file_path") or "keyword" in str(payload.get("prompt", "")).lower():
            action = "generate_keywords"
        elif payload.get("pdf_filename"):
            # Default to patent search for backward compatibility
            action = "search_patents"
        else:
            yield {"error": "Unable to determine action. Please specify 'action' field or provide appropriate payload structure."}
            return
    
    print(f"🎯 Orchestrator: Determined action: {action}")
    
    # Route to appropriate agent
    if action == "generate_keywords":
        async for event in handle_keyword_generation(payload):
            yield event
    elif action == "search_patents":
        async for event in handle_patentview_search(payload):
            yield event
    elif action == "search_articles":
        async for event in handle_scholarly_search(payload):
            yield event
    else:
        yield {"error": f"Unknown action: {action}. Supported actions: 'generate_keywords', 'search_patents', 'search_articles'"}

# =============================================================================
# BEDROCK AGENT CORE APP
# =============================================================================

app = BedrockAgentCoreApp()

@app.entrypoint
async def invoke(payload: Dict[str, Any]):
    """AgentCore streaming entrypoint for the orchestrator."""
    async for event in handle_orchestrator_request(payload):
        yield event

if __name__ == "__main__":
    app.run()