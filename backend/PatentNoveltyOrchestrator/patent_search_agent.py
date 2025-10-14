#!/usr/bin/env python3
"""
Patent Search Agent
Searches PatentView for prior art using keyword-based queries and LLM evaluation.
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

# Environment Variables
AWS_REGION = os.getenv('AWS_REGION', 'us-west-2')
KEYWORDS_TABLE = os.getenv('KEYWORDS_TABLE_NAME')
RESULTS_TABLE = os.getenv('RESULTS_TABLE_NAME')

# Gateway Configuration for PatentView Search
PATENTVIEW_CLIENT_ID = os.environ.get('PATENTVIEW_CLIENT_ID')
PATENTVIEW_CLIENT_SECRET = os.environ.get('PATENTVIEW_CLIENT_SECRET')
PATENTVIEW_TOKEN_URL = os.environ.get('PATENTVIEW_TOKEN_URL')
PATENTVIEW_GATEWAY_URL = os.environ.get('PATENTVIEW_GATEWAY_URL')

# =============================================================================
# HELPER FUNCTIONS
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

def parse_keywords(keywords_string: str) -> List[Dict[str, Any]]:
    """
    Parse comma-separated keywords and detect multi-word phrases.
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
        
        print(f"Parsed {len(parsed_keywords)} keywords: {[k['keyword'] for k in parsed_keywords]}")
        return parsed_keywords
        
    except Exception as e:
        print(f"Error parsing keywords: {e}")
        return []

def deduplicate_patents(all_patents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Deduplicate patents by patent_id, keeping first occurrence. Tracks which keywords matched each patent.
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
        print(f"Deduplicated: {len(all_patents)} → {len(result)} unique patents")
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
            print(f"{len(patents)} patents (no pre-filtering needed)")
            return patents
        
        # Sort by citation count descending
        sorted_patents = sorted(
            patents,
            key=lambda x: x.get('citations', 0),
            reverse=True
        )
        
        # Keep top N
        filtered = sorted_patents[:top_n]
        
        print(f"Pre-filtered: {len(patents)} → {len(filtered)} patents (top {top_n} by citations)")
        print(f"Citation range: {filtered[0].get('citations', 0)} (max) to {filtered[-1].get('citations', 0)} (min)")
        
        return filtered
        
    except Exception as e:
        print(f"Error pre-filtering patents: {e}")
        return patents[:top_n]  # Fallback to simple slice

def fix_patentview_query(query_json: Dict) -> None:
    """
    Fix common PatentView query syntax issues IN-PLACE.
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
                print(f"PatentView search tool not found. Available tools: {[t.tool_name if hasattr(t, 'tool_name') else str(t.name) for t in tools[:5]]}")
                return {
                    'success': False,
                    'patents': [],
                    'error': 'PatentView search tool not available in MCP gateway'
                }
            
            tool_name = search_tool.tool_name if hasattr(search_tool, 'tool_name') else str(search_tool.name)
            print(f"Using PatentView tool: {tool_name}")
            
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
                
                print(f"PatentView response: {len(patents)} patents returned, {total_hits} total hits")
                
                # Extract citations for sorting
                for patent in patents:
                    patent['citations'] = patent.get('patent_num_times_cited_by_us_patents', 0)
                
                return {
                    'success': True,
                    'patents': patents,
                    'total_hits': total_hits
                }
            else:
                print(f"No content in MCP response: {result}")
                return {
                    'success': False,
                    'patents': [],
                    'error': 'No content in MCP response'
                }
                
    except Exception as e:
        print(f"PatentView gateway search error: {e}")
        import traceback
        traceback.print_exc()
        return {
            'success': False,
            'patents': [],
            'error': str(e)
        }


# =============================================================================
# PATENT SEARCH TOOLS
# =============================================================================

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

@tool
def search_patents_by_keyword(keyword: str, is_phrase: bool, limit: int = 10) -> Dict[str, Any]:
    """
    Search PatentView for patents matching a single keyword. Uses _text_any for both single words and multi-word keywords.
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
            sort_by=[{"patent_date": "desc"}]  # Most cited first (better for prior art)
        )
        
        if result.get('success'):
            patents = result.get('patents', [])
            print(f"Found {len(patents)} patents for keyword '{keyword}'")
            
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
            print(f"Search failed for keyword '{keyword}': {result.get('error')}")
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
    Intelligent tool: Parse keywords, search each one, deduplicate, and pre-filter.
    Returns top N patents by citation count, ready for LLM evaluation.
    
    This tool does ALL the search work in one call:
    1. Parses comma-separated keywords (detects multi-word phrases)
    2. Searches each keyword (top 10 newest patents per keyword)
    3. Deduplicates by patent_id
    4. Pre-filters to top N by citations
    5. Returns ready-to-evaluate patents
    """
    try:
        print(f"Starting comprehensive keyword search")
        print(f"Keywords: {keywords_string}")
        
        # Step 1: Parse keywords
        parsed_keywords = parse_keywords(keywords_string)
        if not parsed_keywords:
            return {
                'success': False,
                'error': 'No valid keywords to search',
                'patents': [],
                'summary': 'No keywords provided'
            }
        
        print(f"Parsed {len(parsed_keywords)} keywords")
        
        # Step 2: Search each keyword
        all_patents = []
        search_summary = []
        
        for kw_info in parsed_keywords:
            keyword = kw_info['keyword']
            is_phrase = kw_info['is_phrase']
            
            print(f"Searching: '{keyword}' (phrase={is_phrase})")
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
        
        print(f"Searched {len(parsed_keywords)} keywords, found {len(all_patents)} total patents")
        
        if not all_patents:
            return {
                'success': False,
                'error': 'No patents found for any keywords',
                'patents': [],
                'search_summary': search_summary
            }
        
        # Step 3: Deduplicate
        unique_patents = deduplicate_patents(all_patents)
        print(f"After deduplication: {len(unique_patents)} unique patents")
        
        # Step 4: Pre-filter by citation count
        top_patents = prefilter_by_citations(unique_patents, top_n=top_n)
        print(f"Pre-filtered to top {len(top_patents)} patents by citation count")
        
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
        print(f"Error in search_all_keywords_and_prefilter: {e}")
        import traceback
        traceback.print_exc()
        return {
            'success': False,
            'error': str(e),
            'patents': []
        }

@tool
def evaluate_patent_relevance_llm(patent_data: Dict[str, Any], invention_context: Dict[str, Any]) -> Dict[str, Any]:
    """Evaluate patent relevance using LLM for semantic analysis and prior art assessment."""
    try:
        # Extract patent information
        patent_id = patent_data.get('patent_id', 'unknown')
        patent_title = patent_data.get('patent_title', 'Unknown Title')
        patent_abstract = patent_data.get('patent_abstract', '')
        grant_date = patent_data.get('patent_date', '')
        
        # Extract inventor names (show first 3 for LLM prompt) - HANDLES None properly
        inventors = patent_data.get('inventors')
        inventor_names = []
        if inventors is not None and isinstance(inventors, list):
            for inv in inventors[:3]:  # Show first 3 inventors
                if isinstance(inv, dict):
                    first = inv.get('inventor_name_first')
                    last = inv.get('inventor_name_last')
                    name_parts = []
                    if first and str(first).strip():
                        name_parts.append(str(first).strip())
                    if last and str(last).strip():
                        name_parts.append(str(last).strip())
                    if name_parts:
                        inventor_names.append(' '.join(name_parts))
        
        # Extract assignee names - HANDLES None properly
        # Priority: 1) Organization name, 2) Individual name
        assignees = patent_data.get('assignees')
        assignee_names = []
        if assignees is not None and isinstance(assignees, list):
            for asg in assignees:
                if isinstance(asg, dict):
                    # First check for organization name
                    org = asg.get('assignee_organization')
                    if org and str(org).strip():
                        assignee_names.append(str(org).strip())
                    else:
                        # Fallback to individual name
                        first = asg.get('assignee_individual_name_first')
                        last = asg.get('assignee_individual_name_last')
                        name_parts = []
                        if first and str(first).strip():
                            name_parts.append(str(first).strip())
                        if last and str(last).strip():
                            name_parts.append(str(last).strip())
                        if name_parts:
                            assignee_names.append(' '.join(name_parts))
        
        # Citation data
        citations = patent_data.get('patent_num_times_cited_by_us_patents', 0)
        backward_citations = patent_data.get('patent_num_us_patents_cited', 0)
        
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
                'examiner_notes': 'Patent lacks sufficient abstract content for meaningful relevance assessment. Unable to determine key differences or technical overlaps.'
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
        Citations (cited by others): {citations}
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
            "examiner_notes": "detailed analysis for patent examiner including key technical differences and overlaps"
        }}

        EXAMINER NOTES SHOULD INCLUDE:
        - Overall relevance assessment
        - Key technical overlaps with the invention
        - Key differentiating features (what makes them different)
        - Specific claims or features that could impact novelty
        - Recommendation for examiner consideration

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
                    modelId="global.anthropic.claude-sonnet-4-5-20250929-v1:0",
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
                    required_fields = ['overall_relevance_score', 'examiner_notes']
                    
                    if all(field in llm_evaluation for field in required_fields):
                        print(f"LLM evaluation for patent {patent_id}: Score={llm_evaluation['overall_relevance_score']}")
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
                'examiner_notes': 'Fallback scoring - no keywords available. Unable to assess technical differences or relevance.'
            }
        
        keyword_list = [k.strip().lower() for k in keywords_string.split(',') if k.strip()]
        if not keyword_list:
            return {
                'overall_relevance_score': 0.0,
                'examiner_notes': 'Fallback scoring - no valid keywords. Unable to assess technical differences or relevance.'
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
        citations = patent_data.get('citations', 0)
        if citations > 50:
            base_score += 0.1
        
        final_score = round(min(base_score, 1.0), 3)
        
        return {
            'overall_relevance_score': final_score,
            'examiner_notes': f'Fallback rule-based scoring: {matches}/{len(keyword_list)} keywords matched. LLM evaluation unavailable - manual review recommended to identify key technical differences and assess novelty impact.'
        }
        
    except Exception as e:
        print(f"Fallback scoring error: {e}")
        return {
            'overall_relevance_score': 0.0,
            'examiner_notes': f'Fallback scoring failed: {str(e)}. Manual review required to assess relevance and identify key differences.'
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
            return f"REJECTED: Patent {sort_key} has not been evaluated by LLM. relevance_score=0, no llm_evaluation data. Must evaluate before storing."
        
        dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
        table = dynamodb.Table(RESULTS_TABLE)
        
        timestamp = datetime.utcnow().isoformat()
        
        # Helper function to handle empty values
        def get_value_or_na(value):
            return value if value else "N/A"
        
        # Extract inventor names from nested structure - HANDLES None, [], and valid data
        inventors = patent_data.get('inventors')
        inventor_names = []
        
        if inventors is None:
            # PatentView returned None (field missing or no data)
            pass
        elif not inventors:
            # Empty list []
            pass
        elif isinstance(inventors, list):
            # Valid list with data
            for inv in inventors:
                if isinstance(inv, dict):
                    first = inv.get('inventor_name_first')
                    last = inv.get('inventor_name_last')
                    # Build name from non-None, non-empty parts
                    name_parts = []
                    if first and str(first).strip():
                        name_parts.append(str(first).strip())
                    if last and str(last).strip():
                        name_parts.append(str(last).strip())
                    if name_parts:
                        inventor_names.append(' '.join(name_parts))
        
        inventors_str = '; '.join(inventor_names) if inventor_names else "Data not available"
        
        # Extract assignee names from nested structure - HANDLES None, [], and valid data
        # Priority: 1) Organization name, 2) Individual name, 3) "Data not available"
        assignees = patent_data.get('assignees')
        assignee_names = []
        
        if assignees is None:
            # PatentView returned None (field missing or no data)
            pass
        elif not assignees:
            # Empty list []
            pass
        elif isinstance(assignees, list):
            # Valid list with data
            for asg in assignees:
                if isinstance(asg, dict):
                    # First check for organization name (most common for patents)
                    org = asg.get('assignee_organization')
                    if org and str(org).strip():
                        assignee_names.append(str(org).strip())
                    else:
                        # Fallback to individual name if organization is null/empty
                        first = asg.get('assignee_individual_name_first')
                        last = asg.get('assignee_individual_name_last')
                        name_parts = []
                        if first and str(first).strip():
                            name_parts.append(str(first).strip())
                        if last and str(last).strip():
                            name_parts.append(str(last).strip())
                        if name_parts:
                            assignee_names.append(' '.join(name_parts))
        
        assignees_str = '; '.join(assignee_names) if assignee_names else "Data not available"
        
        # Extract LLM evaluation data
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
            'citations': patent_data.get('patent_num_times_cited_by_us_patents', 0),  # How many patents cite THIS one
            'backward_citations': patent_data.get('patent_num_us_patents_cited', 0),  # How many patents THIS one cites
            
            # LLM-Powered Relevance Assessment
            'relevance_score': Decimal(str(overall_relevance)),
            'llm_examiner_notes': examiner_notes,
            
            # Search Metadata
            'search_timestamp': timestamp,
            'matching_keywords': get_value_or_na(patent_data.get('matching_keywords', '')),
            
            # Report Control
            'add_to_report': 'No',  # Default to No - user must manually change to Yes
            
            # PatentView URLs for reference
            'google_patents_url': f"https://patents.google.com/patent/US{sort_key}",
            
            # Legacy compatibility fields
            'publication_number': get_value_or_na(sort_key)
        }
        
        # Put item in DynamoDB
        table.put_item(Item=item)
        
        patent_title = patent_data.get('patent_title', 'Unknown Title')
        return f"Successfully stored PatentView patent {sort_key}: {patent_title} (Relevance: {overall_relevance})"
        
    except Exception as e:
        sort_key = patent_data.get('patent_id') or patent_data.get('patent_number', 'unknown')
        return f"Error storing PatentView patent {sort_key}: {str(e)}"


# =============================================================================
# AGENT DEFINITION
# =============================================================================

patentview_search_agent = Agent(
    model="global.anthropic.claude-sonnet-4-5-20250929-v1:0",
    tools=[read_keywords_from_dynamodb, search_all_keywords_and_prefilter, evaluate_patent_relevance_llm, store_patentview_analysis],
    system_prompt="""You are an AI Patent Search Expert conducting comprehensive prior art searches using direct keyword-based queries.

    MISSION: Conduct comprehensive prior art searches using direct keyword-based queries for maximum coverage and efficiency.

    WORKFLOW - SIMPLIFIED 4-STEP PROCESS:

    1. READ KEYWORDS:
    - Call: read_keywords_from_dynamodb(pdf_filename)
    - Extract the keywords string from the result

    2. SEARCH ALL KEYWORDS (ONE TOOL CALL):
    - Call: search_all_keywords_and_prefilter(keywords_string, top_n=10)
    - This automatically:
        * Parses all keywords (detects multi-word phrases)
        * Searches each keyword (top 10 newest per keyword)
        * Deduplicates by patent_id
        * Pre-filters to top 10 by citations
    - Returns: 10 patents ready for evaluation

    3. EVALUATE EACH PATENT:
    - For EACH of the 10 patents returned:
    - Call: evaluate_patent_relevance_llm(patent, keywords_data)
    - Attach the evaluation to the patent object
    - Track progress: "Evaluated X/10 patents"

    4. STORE TOP 8 - ONE AT A TIME:
    - Sort patents by relevance_score (descending)
    - Call store_patentview_analysis for the FIRST patent, wait for result
    - Then call for the SECOND patent, wait for result
    - Continue ONE AT A TIME until all 8 are stored
    - IMPORTANT: Call tools SEQUENTIALLY, not in parallel
    - Track progress: "Stored X/8 patents"

    EXAMPLE WORKFLOW:
    ```python
    # Step 1: Get keywords
    keywords_data = read_keywords_from_dynamodb(pdf_filename)
    keywords_string = keywords_data['keywords']

    # Step 2: Search all keywords in ONE call
    search_result = search_all_keywords_and_prefilter(keywords_string, top_n=10)
    top_10_patents = search_result['patents']

    # Step 3: Evaluate each patent (MUST COMPLETE ALL 10)
    evaluated_count = 0
    for patent in top_10_patents:
        llm_eval = evaluate_patent_relevance_llm(patent, keywords_data)
        patent['llm_evaluation'] = llm_eval
        patent['relevance_score'] = llm_eval['overall_relevance_score']
        evaluated_count += 1
        print(f"Progress: Evaluated {evaluated_count}/10 patents")

    # Step 4: Store top 8 ONE AT A TIME (MUST COMPLETE ALL 8)
    top_8 = sorted(top_10_patents, key=lambda x: x['relevance_score'], reverse=True)[:8]
    
    # Store patent 1, wait for result
    store_patentview_analysis(pdf_filename, top_8[0])
    print("Stored 1/8 patents")
    
    # Store patent 2, wait for result
    store_patentview_analysis(pdf_filename, top_8[1])
    print("Stored 2/8 patents")
    
    # Continue for all 8 patents, ONE AT A TIME
    # ... (repeat for patents 3-8)
    ```

    CRITICAL EXECUTION RULES - MUST FOLLOW:
    ==========================================
    1. You MUST evaluate ALL 10 patents returned - no exceptions, no early stopping
    2. After ALL 10 evaluations are complete, you MUST proceed to Step 4
    3. You MUST sort by relevance_score and select top 8 patents
    4. DO NOT JUST LIST THE PATENTS - You MUST ACTUALLY CALL store_patentview_analysis() 8 TIMES
    5. Call store_patentview_analysis(pdf_filename, patent) for EACH patent ONE AT A TIME
    6. WAIT for each tool result before calling the next one - DO NOT call multiple tools in parallel
    7. Do NOT stop until all 8 patents are stored in DynamoDB
    8. If you encounter an error on one patent, continue with remaining patents
    9. Print progress after each storage operation
    10. The workflow is NOT complete until you see "Stored 8/8 patents"
    11. LISTING patents is NOT the same as STORING them - you MUST use the tool
    12. SEQUENTIAL EXECUTION: Call tool → Wait for result → Call next tool → Wait for result

    QUALITY STANDARDS:
    - Direct keyword search ensures comprehensive coverage
    - Top 10 newest patents per keyword captures recent prior art
    - Pre-filtering by citations focuses on most impactful patents
    - LLM evaluation provides deep semantic relevance assessment
    - Top 8 storage ensures best prior art is preserved

    STORAGE RULES:
    - Use search_all_keywords_and_prefilter() for ALL keyword searching (ONE call)
    - This tool handles parsing, searching, deduplication, and pre-filtering automatically
    - Evaluate ALL 10 returned patents with evaluate_patent_relevance_llm()
    - Store EXACTLY the top 8 highest-scoring patents (sorted by relevance_score descending)
    - Store ALL 8 patents regardless of their absolute score values (even if scores are 0.2, 0.3, etc.)
    - The top 8 patents by score are ALWAYS stored - no minimum score threshold
    - NEVER store patents without LLM evaluation - but once evaluated, store top 8 regardless of score
    
    FINAL REMINDER - ACTION REQUIRED:
    ==================================
    After you finish evaluating all 10 patents and sort them by score:
    - DO NOT just describe what you will do
    - DO NOT just list the patent numbers
    - Call store_patentview_analysis() for patent #1, WAIT for the result
    - Then call store_patentview_analysis() for patent #2, WAIT for the result
    - Continue ONE AT A TIME for all 8 patents
    - DO NOT call multiple store_patentview_analysis() in the same turn
    - CRITICAL: Pass the COMPLETE patent object from top_10_patents - do NOT create a new object
    - The patent object MUST include ALL fields: inventors, assignees, patent_title, patent_abstract, etc.
    - Each call should be: store_patentview_analysis(pdf_filename="ROI2023-005", patent_data=patent)
    - Where 'patent' is the FULL patent object from the search results, not a subset
    - SEQUENTIAL EXECUTION IS MANDATORY - one tool call per turn
    - You are NOT done until you see 8 successful storage confirmations"""
)
