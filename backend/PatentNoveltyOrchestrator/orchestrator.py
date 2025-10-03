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
# USPTO SEARCH TOOLS
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

@tool
def generate_patent_search_strategies_llm(invention_context: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Generate strategic PatentView search queries using LLM analysis of the invention."""
    try:
        # Extract invention context
        title = invention_context.get('title', '')
        tech_description = invention_context.get('technology_description', '')
        tech_applications = invention_context.get('technology_applications', '')
        keywords_string = invention_context.get('keywords', '')
        
        if not keywords_string:
            print("No keywords provided for search strategy generation")
            return []
        
        # Create LLM prompt for patent search strategy generation
        strategy_generation_prompt = f"""You are a patent search expert with deep knowledge of PatentView API syntax and patent prior art discovery.

INVENTION CONTEXT:
Title: {title}
Technology Description: {tech_description}
Applications: {tech_applications}
Keywords: {keywords_string}

CRITICAL PATENTVIEW QUERY SYNTAX RULES:
1. Text operators (_text_any, _text_all, _text_phrase) MUST use STRING values, NOT arrays
   ✅ CORRECT: {{"_text_any": {{"patent_title": "machine learning neural network"}}}}
   ❌ WRONG: {{"_text_any": {{"patent_title": ["machine", "learning"]}}}}

2. For non-text operators, arrays ARE allowed:
   ✅ CORRECT: {{"inventors.inventor_name_last": ["Smith", "Jones"]}}

3. Available operators:
   - Text search: _text_any, _text_all, _text_phrase (STRING values only!)
   - Logical: _and, _or, _not
   - Comparison: _eq, _neq, _gt, _gte, _lt, _lte
   - Fields: patent_title, patent_abstract, patent_date, patent_type

4. Examples of VALID queries:
   - {{"_text_any": {{"patent_title": "biodegradable polymer"}}}}
   - {{"_and": [{{"_text_any": {{"patent_abstract": "machine learning"}}}}, {{"_gte": {{"patent_date": "2015-01-01"}}}}]}}
   - {{"_or": [{{"_text_phrase": {{"patent_title": "neural network"}}}}, {{"_text_any": {{"patent_abstract": "deep learning"}}}}]}}

PATENT SEARCH STRATEGY:
Generate EXACTLY 3 strategic PatentView queries that maximize prior art discovery:
1. Core technology search (most specific to invention)
2. Application domain search (use case/industry)
3. Broader technology search (related concepts)

Focus on the most impactful searches. Quality over quantity.

RESPOND IN THIS EXACT JSON FORMAT (3 strategies only):
[
    {{
        "query_json": {{"_text_any": {{"patent_title": "neural network medical"}}}},
        "strategy_type": "core_technology",
        "rationale": "Direct search for core AI medical technology",
        "expected_relevance": "high",
        "search_scope": "targeted"
    }},
    {{
        "query_json": {{"_or": [{{"_text_any": {{"patent_title": "diagnostic system"}}}}, {{"_text_any": {{"patent_abstract": "medical diagnosis"}}}}]}},
        "strategy_type": "application_domain",
        "rationale": "Search for medical diagnostic applications",
        "expected_relevance": "medium",
        "search_scope": "medium"
    }},
    {{
        "query_json": {{"_text_any": {{"patent_abstract": "artificial intelligence healthcare"}}}},
        "strategy_type": "broader_technology",
        "rationale": "Broader AI healthcare technology search",
        "expected_relevance": "medium",
        "search_scope": "broad"
    }}
]

Generate EXACTLY 3 diverse strategies. Remember: text operators use STRINGS, not arrays!"""

        try:
            # Make LLM call for strategy generation
            bedrock_client = boto3.client('bedrock-runtime', region_name=AWS_REGION)
            request_body = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 3000,
                "messages": [
                    {
                        "role": "user",
                        "content": strategy_generation_prompt
                    }
                ]
            }
            
            response = bedrock_client.invoke_model(
                modelId="us.anthropic.claude-3-7-sonnet-20250219-v1:0",
                body=json.dumps(request_body)
            )
            
            response_body = json.loads(response['body'].read())
            llm_response = response_body['content'][0]['text']
            print(f"LLM Strategy Response: {llm_response[:200]}...")
            
            # Parse JSON from LLM response
            json_start = llm_response.find('[')
            json_end = llm_response.rfind(']') + 1
            if json_start != -1 and json_end != -1:
                json_str = llm_response[json_start:json_end]
                search_strategies = json.loads(json_str)
                
                # Validate each strategy has required fields
                validated_strategies = []
                for strategy in search_strategies:
                    if all(key in strategy for key in ['query_json', 'strategy_type', 'rationale']):
                        validated_strategies.append(strategy)
                    else:
                        print(f"Invalid strategy format: {strategy}")
                
                print(f"✅ Generated {len(validated_strategies)} patent search strategies")
                return validated_strategies
            else:
                print("Could not find JSON in LLM strategy response")
                return []
                
        except Exception as e:
            print(f"LLM strategy generation failed: {e}")
            # Fallback to simple static approach
            return generate_fallback_patent_strategies(keywords_string)
            
    except Exception as e:
        print(f"Error in patent search strategy generation: {e}")
        return []

def generate_fallback_patent_strategies(keywords_string: str) -> List[Dict[str, Any]]:
    """Simple fallback strategy generation when LLM fails."""
    try:
        keyword_list = [k.strip() for k in keywords_string.split(',') if k.strip()]
        if not keyword_list:
            return []
        
        strategies = []
        
        # Core technology search
        if len(keyword_list) >= 1:
            strategies.append({
                "query_json": {"_text_any": {"patent_title": keyword_list[0]}},
                "strategy_type": "core_technology",
                "rationale": f"Direct search for {keyword_list[0]}",
                "expected_relevance": "high",
                "search_scope": "broad"
            })
        
        # Combined search
        if len(keyword_list) >= 2:
            strategies.append({
                "query_json": {"_or": [
                    {"_text_any": {"patent_title": f"{keyword_list[0]} {keyword_list[1]}"}},
                    {"_text_any": {"patent_abstract": f"{keyword_list[0]} {keyword_list[1]}"}}
                ]},
                "strategy_type": "combination",
                "rationale": f"Combined search for {keyword_list[0]} and {keyword_list[1]}",
                "expected_relevance": "medium",
                "search_scope": "medium"
            })
        
        return strategies[:3]  # Limit fallback to 3 strategies
        
    except Exception as e:
        print(f"Fallback strategy generation failed: {e}")
        return []

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
def assess_patent_search_quality_llm(search_results: Dict[str, Any], search_strategy: Dict[str, Any], invention_context: Dict[str, Any]) -> Dict[str, Any]:
    """Assess the quality of patent search results and determine if refinement is needed."""
    try:
        patents = search_results.get('patents', [])
        total_hits = search_results.get('total_hits', 0)
        strategy_type = search_strategy.get('strategy_type', 'unknown')
        query_json = search_strategy.get('query_json', {})
        
        # Extract invention context
        invention_title = invention_context.get('title', '')
        keywords = invention_context.get('keywords', '')
        
        # Quick quality checks
        if total_hits == 0:
            return {
                'quality_assessment': 'poor',
                'issues_identified': ['No results found - query may be too specific or use uncommon terms'],
                'refinement_action': 'broaden',
                'refinement_rationale': 'Zero results indicate query is too restrictive',
                'should_refine': True
            }
        
        if total_hits > 5000:
            return {
                'quality_assessment': 'needs_refinement',
                'issues_identified': ['Too many results - query is too broad'],
                'refinement_action': 'narrow',
                'refinement_rationale': 'Excessive results indicate query lacks specificity',
                'should_refine': True
            }
        
        if len(patents) < 3:
            return {
                'quality_assessment': 'needs_refinement',
                'issues_identified': ['Very few results returned - try broader or alternative terms'],
                'refinement_action': 'alternative_terms',
                'refinement_rationale': 'Limited results suggest need for different terminology',
                'should_refine': True
            }
        
        # Calculate quality metrics
        patents_with_abstracts = sum(1 for p in patents if p.get('patent_abstract') and len(p.get('patent_abstract', '')) > 50)
        abstract_ratio = patents_with_abstracts / len(patents) if patents else 0
        
        avg_citation_count = sum(p.get('citation_count', 0) for p in patents) / len(patents) if patents else 0
        
        # Check patent type diversity
        patent_types = set(p.get('patent_type', 'unknown') for p in patents)
        
        # LLM-based quality assessment for borderline cases (DISABLED for performance)
        # Skip LLM quality assessment to reduce execution time
        if False and 10 <= total_hits <= 5000 and len(patents) >= 3 and abstract_ratio > 0.5:
            # Use LLM for deeper quality analysis
            quality_prompt = f"""Analyze the quality of these patent search results for refinement decision.

INVENTION CONTEXT:
Title: {invention_title}
Keywords: {keywords}

SEARCH STRATEGY:
Type: {strategy_type}
Query: {query_json}

RESULTS SUMMARY:
- Total patents found: {total_hits}
- Patents returned: {len(patents)}
- Patents with abstracts: {patents_with_abstracts} ({abstract_ratio:.1%})
- Average citation count: {avg_citation_count:.1f}
- Patent types: {', '.join(patent_types)}

SAMPLE PATENT TITLES (first 5):
{chr(10).join(f"- {p.get('patent_title', 'Unknown')}" for p in patents[:5])}

QUALITY ASSESSMENT TASK:
Determine if these results are high-quality for prior art discovery or if query refinement would improve results.

Consider:
1. Result quantity (too few/many vs optimal range)
2. Result relevance (do titles match invention domain?)
3. Result diversity (multiple assignees, patent types)
4. Citation quality (are these impactful patents?)
5. Abstract availability (needed for relevance assessment)

RESPOND IN JSON FORMAT:
{{
    "quality_assessment": "excellent|good|needs_refinement|poor",
    "issues_identified": ["list of specific issues if any"],
    "refinement_action": "none|broaden|narrow|alternative_terms|temporal_adjustment",
    "refinement_rationale": "explanation of assessment",
    "should_refine": true|false
}}"""

            try:
                bedrock_client = boto3.client('bedrock-runtime', region_name=AWS_REGION)
                request_body = {
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 800,
                    "messages": [{"role": "user", "content": quality_prompt}]
                }
                
                response = bedrock_client.invoke_model(
                    modelId="us.anthropic.claude-3-7-sonnet-20250219-v1:0",
                    body=json.dumps(request_body)
                )
                
                response_body = json.loads(response['body'].read())
                llm_response = response_body['content'][0]['text']
                
                # Parse JSON
                json_start = llm_response.find('{')
                json_end = llm_response.rfind('}') + 1
                if json_start != -1 and json_end != -1:
                    json_str = llm_response[json_start:json_end]
                    quality_assessment = json.loads(json_str)
                    print(f"✅ LLM quality assessment for {strategy_type}: {quality_assessment['quality_assessment']}")
                    return quality_assessment
                    
            except Exception as e:
                print(f"LLM quality assessment failed: {e}")
                # Fallback to rule-based assessment
                pass
        
        # Default assessment for good results
        return {
            'quality_assessment': 'good',
            'issues_identified': [],
            'refinement_action': 'none',
            'refinement_rationale': f'Results are within acceptable range ({total_hits} total, {len(patents)} returned)',
            'should_refine': False
        }
        
    except Exception as e:
        print(f"Error assessing patent search quality: {e}")
        return {
            'quality_assessment': 'good',
            'issues_identified': [],
            'refinement_action': 'none',
            'refinement_rationale': 'Assessment failed - proceeding with current results',
            'should_refine': False
        }

@tool
def refine_patent_query_llm(original_strategy: Dict[str, Any], quality_issues: Dict[str, Any], invention_context: Dict[str, Any]) -> Dict[str, Any]:
    """Refine patent search query using LLM based on quality assessment."""
    try:
        original_query = original_strategy.get('query_json', {})
        strategy_type = original_strategy.get('strategy_type', 'unknown')
        refinement_action = quality_issues.get('refinement_action', 'none')
        issues = quality_issues.get('issues_identified', [])
        
        # Extract invention context
        invention_title = invention_context.get('title', '')
        tech_description = invention_context.get('technology_description', '')
        keywords = invention_context.get('keywords', '')
        
        refinement_prompt = f"""Refine this PatentView query to address the identified quality issues.

INVENTION CONTEXT:
Title: {invention_title}
Technology: {tech_description}
Keywords: {keywords}

ORIGINAL SEARCH STRATEGY:
Type: {strategy_type}
Query: {json.dumps(original_query, indent=2)}

QUALITY ISSUES:
{chr(10).join(f"- {issue}" for issue in issues)}

REFINEMENT ACTION NEEDED: {refinement_action}

PATENTVIEW QUERY SYNTAX:
- Text operators: _text_any, _text_all, _text_phrase
- Fields: patent_title, patent_abstract
- Logical: _and, _or, _not
- Example: {{"_text_any": {{"patent_title": "machine learning"}}}}

REFINEMENT STRATEGIES:
- Broaden: Use _text_any instead of _text_all, fewer required terms, search in both title and abstract
- Narrow: Add more specific terms, use _text_phrase for exact matches, focus on title only
- Alternative terms: Use synonyms, technical variations, different terminology
- Temporal: Add date filters for recent/historical patents

Generate an improved PatentView JSON query that addresses the issues while maintaining search intent.

RESPOND IN JSON FORMAT:
{{
    "query_json": {{"_text_any": {{"patent_title": "improved query"}}}},
    "strategy_type": "{strategy_type}_refined",
    "rationale": "explanation of refinement",
    "expected_relevance": "high|medium|low",
    "search_scope": "broad|medium|narrow"
}}"""

        try:
            bedrock_client = boto3.client('bedrock-runtime', region_name=AWS_REGION)
            request_body = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 1000,
                "messages": [{"role": "user", "content": refinement_prompt}]
            }
            
            response = bedrock_client.invoke_model(
                modelId="us.anthropic.claude-3-7-sonnet-20250219-v1:0",
                body=json.dumps(request_body)
            )
            
            response_body = json.loads(response['body'].read())
            llm_response = response_body['content'][0]['text']
            
            # Parse JSON
            json_start = llm_response.find('{')
            json_end = llm_response.rfind('}') + 1
            if json_start != -1 and json_end != -1:
                json_str = llm_response[json_start:json_end]
                refined_strategy = json.loads(json_str)
                
                # Validate refined query
                if validate_patentview_query(refined_strategy.get('query_json', {})):
                    print(f"✅ Refined query for {strategy_type}: {refined_strategy['query_json']}")
                    return refined_strategy
                else:
                    print(f"Refined query validation failed for {strategy_type}")
                    return {"error": "Refined query validation failed"}
                    
        except Exception as e:
            print(f"LLM query refinement failed: {e}")
            return {"error": f"Query refinement failed: {str(e)}"}
            
    except Exception as e:
        print(f"Error refining patent query: {e}")
        return {"error": f"Refinement error: {str(e)}"}

@tool
def execute_adaptive_patent_search(search_strategy: Dict[str, Any], invention_context: Dict[str, Any], limit: int = 100, max_refinements: int = 1) -> Dict[str, Any]:
    """Execute adaptive PatentView search with automatic quality assessment and refinement."""
    try:
        strategy_type = search_strategy.get('strategy_type', 'unknown')
        print(f"🔍 Starting adaptive search for strategy: {strategy_type}")
        
        current_strategy = search_strategy
        refinement_count = 0
        best_result = None
        
        while refinement_count <= max_refinements:
            # Execute search with current strategy
            search_result = execute_strategic_patent_search(current_strategy, limit)
            
            if not search_result.get('success'):
                print(f"Search failed for {strategy_type}: {search_result.get('error')}")
                if best_result:
                    return best_result
                return search_result
            
            # Assess search quality
            quality_assessment = assess_patent_search_quality_llm(search_result, current_strategy, invention_context)
            
            print(f"Quality assessment for {strategy_type} (attempt {refinement_count + 1}): {quality_assessment['quality_assessment']}")
            
            # Store current result as best if it's good enough
            if quality_assessment['quality_assessment'] in ['excellent', 'good']:
                search_result['quality_assessment'] = quality_assessment
                search_result['refinement_count'] = refinement_count
                return search_result
            
            # Keep best result so far
            if not best_result or len(search_result.get('patents', [])) > len(best_result.get('patents', [])):
                best_result = search_result
                best_result['quality_assessment'] = quality_assessment
                best_result['refinement_count'] = refinement_count
            
            # Check if refinement is needed and possible
            if not quality_assessment.get('should_refine', False) or refinement_count >= max_refinements:
                print(f"Stopping refinement for {strategy_type}: refinement_count={refinement_count}, should_refine={quality_assessment.get('should_refine')}")
                return best_result
            
            # Refine query
            print(f"Refining query for {strategy_type} (attempt {refinement_count + 1}/{max_refinements})")
            refined_strategy = refine_patent_query_llm(current_strategy, quality_assessment, invention_context)
            
            if 'error' in refined_strategy:
                print(f"Query refinement failed: {refined_strategy['error']}")
                return best_result
            
            # Use refined strategy for next iteration
            current_strategy = refined_strategy
            refinement_count += 1
            
            # Add delay to respect rate limits
            time.sleep(1)
        
        # Return best result after max refinements
        print(f"Max refinements reached for {strategy_type}, returning best result")
        return best_result
        
    except Exception as e:
        print(f"Error in adaptive patent search: {e}")
        import traceback
        traceback.print_exc()
        return {"error": f"Adaptive search failed: {str(e)}", "patents": [], "strategy": search_strategy}

@tool
def execute_strategic_patent_search(search_strategy: Dict[str, Any], limit: int = 100) -> Dict[str, Any]:
    """Execute a single strategic PatentView search with the given strategy (internal use)."""
    try:
        query_json = search_strategy.get('query_json', {})
        strategy_type = search_strategy.get('strategy_type', 'unknown')
        
        # Validate query syntax
        if not validate_patentview_query(query_json):
            print(f"Invalid PatentView query syntax for strategy {strategy_type}")
            return {"error": "Invalid query syntax", "patents": [], "strategy": search_strategy}
        
        # Get OAuth access token for PatentView Gateway
        access_token = fetch_patentview_access_token()
        print(f"Got PatentView access token for {strategy_type}: {access_token[:20]}...")
        
        # Create MCP client for PatentView Gateway
        mcp_client = MCPClient(lambda: create_streamable_http_transport(PATENTVIEW_GATEWAY_URL, access_token))
        
        with mcp_client:
            # Get tools with pagination
            tools = get_full_tools_list(mcp_client)
            
            if not tools:
                return {"error": "No PatentView tools available", "patents": [], "strategy": search_strategy}
            
            # Find PatentView search tool
            search_tool = None
            for tool in tools:
                if 'searchPatentsPatentView' in tool.tool_name or 'patent-view___searchPatentsPatentView' in tool.tool_name:
                    search_tool = tool
                    break
            
            if not search_tool:
                return {"error": "PatentView search tool not found", "patents": [], "strategy": search_strategy}
            
            # Convert query to JSON string
            query_json_str = json.dumps(query_json)
            
            # Define fields to return
            fields_json = json.dumps([
                "patent_id", "patent_title", "patent_date", "patent_abstract", "patent_type",
                "patent_num_times_cited_by_us_patents",
                "inventors.inventor_name_first", "inventors.inventor_name_last",
                "assignees.assignee_organization", "assignees.assignee_individual_name_first", "assignees.assignee_individual_name_last"
            ])
            
            # Sort by citation count (most cited first)
            sort_json = json.dumps([{"patent_num_times_cited_by_us_patents": "desc"}])
            
            # Options with size limit
            options_json = json.dumps({"size": min(limit, 1000)})
            
            print(f"Executing {strategy_type} search: {query_json_str}")
            
            # Call the tool with PatentView parameters
            result = mcp_client.call_tool_sync(
                name=search_tool.tool_name,
                arguments={
                    "q": query_json_str,
                    "f": fields_json,
                    "s": sort_json,
                    "o": options_json
                },
                tool_use_id=f"patentview-{strategy_type}-{hash(query_json_str)}"
            )
            
            if result and isinstance(result, dict) and 'content' in result:
                content = result['content']
                if isinstance(content, list) and len(content) > 0:
                    text_content = content[0].get('text', '') if isinstance(content[0], dict) else str(content[0])
                    
                    try:
                        data = json.loads(text_content)
                        
                        if data.get('error') == False and 'patents' in data:
                            patents = data.get('patents', [])
                            total_hits = data.get('total_hits', 0)
                            
                            print(f"✅ {strategy_type} search found {len(patents)} patents (total hits: {total_hits})")
                            
                            # Process PatentView patents
                            processed_patents = []
                            for patent in patents:
                                # Extract inventor names
                                inventors = patent.get('inventors', [])
                                inventor_names = []
                                for inventor in inventors:
                                    first = inventor.get('inventor_name_first', '')
                                    last = inventor.get('inventor_name_last', '')
                                    if first or last:
                                        name = f"{first} {last}".strip()
                                        inventor_names.append(name)
                                
                                # Extract assignee information
                                assignees = patent.get('assignees', [])
                                assignee_names = []
                                for assignee in assignees:
                                    org = assignee.get('assignee_organization', '')
                                    if org:
                                        assignee_names.append(org)
                                    else:
                                        first = assignee.get('assignee_individual_name_first', '')
                                        last = assignee.get('assignee_individual_name_last', '')
                                        if first or last:
                                            name = f"{first} {last}".strip()
                                            assignee_names.append(name)
                                
                                # Map PatentView data to our expected structure
                                processed_patent = {
                                    # Core Identity
                                    'patent_id': patent.get('patent_id', ''),
                                    'patent_number': patent.get('patent_id', ''),
                                    'patent_title': patent.get('patent_title', ''),
                                    'patent_abstract': patent.get('patent_abstract', ''),
                                    
                                    # Dates
                                    'patent_date': patent.get('patent_date', ''),
                                    'grant_date': patent.get('patent_date', ''),
                                    
                                    # Patent Info
                                    'patent_type': patent.get('patent_type', ''),
                                    'citation_count': patent.get('patent_num_times_cited_by_us_patents', 0),
                                    
                                    # People & Organizations
                                    'inventor_names': inventor_names,
                                    'assignee_names': assignee_names,
                                    
                                    # Search metadata
                                    'search_strategy_type': strategy_type,
                                    'search_query_used': query_json_str,
                                    'matching_keywords': str(query_json),
                                    'data_source': 'PatentView'
                                }
                                processed_patents.append(processed_patent)
                            
                            return {
                                "patents": processed_patents,
                                "total_hits": total_hits,
                                "strategy": search_strategy,
                                "success": True
                            }
                        else:
                            error_msg = data.get('error', 'Unknown PatentView API error')
                            print(f"⚠️ PatentView API error for {strategy_type}: {error_msg}")
                            return {"error": error_msg, "patents": [], "strategy": search_strategy}
                            
                    except json.JSONDecodeError as je:
                        print(f"JSON decode error for {strategy_type}: {je}")
                        return {"error": f"JSON parsing failed: {str(je)}", "patents": [], "strategy": search_strategy}
                else:
                    return {"error": "No content in PatentView result", "patents": [], "strategy": search_strategy}
            else:
                return {"error": "No valid PatentView response", "patents": [], "strategy": search_strategy}
                
    except Exception as e:
        print(f"Error executing {strategy_type} patent search: {e}")
        import traceback
        traceback.print_exc()
        return {"error": f"Search execution failed: {str(e)}", "patents": [], "strategy": search_strategy}

@tool
def get_patentview_patent_details(patent_id: str) -> Dict[str, Any]:
    """Get additional patent details from PatentView for a specific patent ID."""
    try:
        print(f"Getting PatentView details for patent: {patent_id}")
        
        # Get OAuth access token for PatentView Gateway
        access_token = fetch_patentview_access_token()
        
        # Create MCP client for PatentView Gateway
        mcp_client = MCPClient(lambda: create_streamable_http_transport(PATENTVIEW_GATEWAY_URL, access_token))
        
        with mcp_client:
            # Get tools with pagination
            tools = get_full_tools_list(mcp_client)
            
            # Find PatentView search tool (we'll use it to get specific patent details)
            search_tool = None
            for tool in tools:
                if 'searchPatentsPatentView' in tool.tool_name or 'patent-view___searchPatentsPatentView' in tool.tool_name:
                    search_tool = tool
                    break
            
            if not search_tool:
                print("No PatentView search tool found for details")
                return {"error": "PatentView search tool not available"}
            
            print(f"Using PatentView tool for details: {search_tool.tool_name}")
            
            # Create query to get specific patent by ID
            patentview_query = json.dumps({"patent_id": patent_id})
            
            # Get comprehensive fields for detailed view
            fields_json = json.dumps([
                "patent_id", "patent_title", "patent_date", "patent_abstract", "patent_type",
                "patent_num_times_cited_by_us_patents", "patent_num_us_patents_cited",
                "patent_processing_days", "patent_earliest_application_date",
                "inventors.inventor_name_first", "inventors.inventor_name_last",
                "assignees.assignee_organization", "assignees.assignee_individual_name_first", "assignees.assignee_individual_name_last",
                "cpc_current.cpc_section", "cpc_current.cpc_class", "cpc_current.cpc_subclass", "cpc_current.cpc_group"
            ])
            
            # Call the tool to get patent details
            result = mcp_client.call_tool_sync(
                name=search_tool.tool_name,
                arguments={
                    "q": patentview_query,
                    "f": fields_json,
                    "o": json.dumps({"size": 1})
                },
                tool_use_id=f"patentview-details-{hash(patent_id)}"
            )
            
            if result and isinstance(result, dict) and 'content' in result:
                content = result['content']
                if isinstance(content, list) and len(content) > 0:
                    text_content = content[0].get('text', '') if isinstance(content[0], dict) else str(content[0])
                    
                    try:
                        data = json.loads(text_content)
                        
                        if data.get('error') == False and 'patents' in data:
                            patents = data.get('patents', [])
                            
                            if patents:
                                patent = patents[0]  # Should be only one patent
                                
                                # Extract CPC classifications
                                cpc_classes = patent.get('cpc_current', [])
                                cpc_info = []
                                for cpc in cpc_classes[:5]:  # Limit to first 5
                                    cpc_str = f"{cpc.get('cpc_section', '')}{cpc.get('cpc_class', '')}{cpc.get('cpc_subclass', '')}{cpc.get('cpc_group', '')}"
                                    if cpc_str.strip():
                                        cpc_info.append(cpc_str)
                                
                                print(f"✅ Found detailed PatentView data for {patent_id}")
                                return {
                                    "patent_id": patent_id,
                                    "detailed_data": patent,
                                    "cpc_classifications": cpc_info,
                                    "processing_days": patent.get('patent_processing_days', 0),
                                    "citations_made": patent.get('patent_num_us_patents_cited', 0),
                                    "citations_received": patent.get('patent_num_times_cited_by_us_patents', 0),
                                    "earliest_filing_date": patent.get('patent_earliest_application_date', ''),
                                    "data_source": "PatentView"
                                }
                            else:
                                return {"error": f"No patent found with ID {patent_id}"}
                        else:
                            return {"error": f"PatentView API error for patent {patent_id}"}
                            
                    except json.JSONDecodeError as je:
                        print(f"JSON decode error in patent details: {je}")
                        return {"error": f"Failed to parse patent details response: {str(je)}"}
                else:
                    print("No content in patent details result")
                    return {"error": "No content in patent details response"}
            else:
                print(f"No content in patent details result: {result}")
                return {"error": "No valid patent details response"}
                
    except Exception as e:
        print(f"Error getting PatentView patent details: {e}")
        import traceback
        traceback.print_exc()
        return {"error": f"Patent details retrieval failed: {str(e)}"}

@tool
def evaluate_patent_relevance_llm(patent_data: Dict[str, Any], invention_context: Dict[str, Any]) -> Dict[str, Any]:
    """Evaluate patent relevance using LLM for semantic analysis and prior art assessment."""
    try:
        # Extract patent information
        patent_id = patent_data.get('patent_id', 'unknown')
        patent_title = patent_data.get('patent_title', 'Unknown Title')
        patent_abstract = patent_data.get('patent_abstract', '')
        grant_date = patent_data.get('grant_date', '')
        assignee_names = patent_data.get('assignee_names', [])
        citation_count = patent_data.get('citation_count', 0)
        patent_type = patent_data.get('patent_type', '')
        
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
                'technical_overlap_score': 0.0,
                'novelty_threat_level': 'none',
                'specific_overlaps': [],
                'key_differences': ['Insufficient patent abstract for analysis'],
                'examiner_notes': 'Patent lacks sufficient abstract content for meaningful relevance assessment',
                'citation_recommendation': 'not_relevant',
                'confidence_level': 'low'
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
Assignee: {', '.join(assignee_names) if assignee_names else 'Unknown'}
Citations: {citation_count}
Patent Type: {patent_type}

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
    "technical_overlap_score": 0.0-1.0,
    "novelty_threat_level": "high|medium|low|none",
    "specific_overlaps": ["list of overlapping features"],
    "key_differences": ["list of differentiating features"],
    "examiner_notes": "detailed analysis for patent examiner",
    "citation_recommendation": "primary_reference|secondary_reference|background_art|not_relevant",
    "confidence_level": "high|medium|low"
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
                    required_fields = ['overall_relevance_score', 'technical_overlap_score', 'novelty_threat_level', 
                                     'specific_overlaps', 'key_differences', 'examiner_notes', 
                                     'citation_recommendation', 'confidence_level']
                    
                    if all(field in llm_evaluation for field in required_fields):
                        print(f"✅ LLM evaluation for patent {patent_id}: Score={llm_evaluation['overall_relevance_score']}, Threat={llm_evaluation['novelty_threat_level']}")
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
                'technical_overlap_score': 0.0,
                'novelty_threat_level': 'none',
                'specific_overlaps': [],
                'key_differences': [],
                'examiner_notes': 'Fallback scoring - no keywords available',
                'citation_recommendation': 'not_relevant',
                'confidence_level': 'low'
            }
        
        keyword_list = [k.strip().lower() for k in keywords_string.split(',') if k.strip()]
        if not keyword_list:
            return {
                'overall_relevance_score': 0.0,
                'technical_overlap_score': 0.0,
                'novelty_threat_level': 'none',
                'specific_overlaps': [],
                'key_differences': [],
                'examiner_notes': 'Fallback scoring - no valid keywords',
                'citation_recommendation': 'not_relevant',
                'confidence_level': 'low'
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
        
        # Determine threat level
        if final_score > 0.7:
            threat_level = 'high'
        elif final_score > 0.4:
            threat_level = 'medium'
        elif final_score > 0.2:
            threat_level = 'low'
        else:
            threat_level = 'none'
        
        return {
            'overall_relevance_score': final_score,
            'technical_overlap_score': final_score * 0.8,
            'novelty_threat_level': threat_level,
            'specific_overlaps': [kw for kw in keyword_list if kw in patent_text],
            'key_differences': [],
            'examiner_notes': f'Fallback rule-based scoring: {matches}/{len(keyword_list)} keywords matched',
            'citation_recommendation': 'secondary_reference' if final_score > 0.5 else 'background_art',
            'confidence_level': 'low'
        }
        
    except Exception as e:
        print(f"Fallback scoring error: {e}")
        return {
            'overall_relevance_score': 0.0,
            'technical_overlap_score': 0.0,
            'novelty_threat_level': 'none',
            'specific_overlaps': [],
            'key_differences': [],
            'examiner_notes': f'Fallback scoring failed: {str(e)}',
            'citation_recommendation': 'not_relevant',
            'confidence_level': 'low'
        }

@tool
def validate_search_coverage_llm(all_patents: List[Dict[str, Any]], invention_context: Dict[str, Any], search_strategies_used: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Validate if patent search has achieved comprehensive prior art coverage."""
    try:
        # Extract invention context
        invention_title = invention_context.get('title', '')
        tech_description = invention_context.get('technology_description', '')
        tech_applications = invention_context.get('technology_applications', '')
        keywords = invention_context.get('keywords', '')
        
        # Analyze collected patents
        total_patents = len(all_patents)
        unique_assignees = set()
        patent_types = {}
        date_range = {'earliest': None, 'latest': None}
        avg_citations = 0
        
        for patent in all_patents:
            # Assignees
            assignees = patent.get('assignee_names', [])
            for assignee in assignees:
                if assignee:
                    unique_assignees.add(assignee)
            
            # Patent types
            ptype = patent.get('patent_type', 'unknown')
            patent_types[ptype] = patent_types.get(ptype, 0) + 1
            
            # Date range
            grant_date = patent.get('grant_date', '')
            if grant_date:
                if not date_range['earliest'] or grant_date < date_range['earliest']:
                    date_range['earliest'] = grant_date
                if not date_range['latest'] or grant_date > date_range['latest']:
                    date_range['latest'] = grant_date
            
            # Citations
            avg_citations += patent.get('citation_count', 0)
        
        avg_citations = avg_citations / total_patents if total_patents > 0 else 0
        
        # Summarize search strategies used
        strategies_summary = []
        for strategy in search_strategies_used:
            strategies_summary.append({
                'type': strategy.get('strategy_type', 'unknown'),
                'rationale': strategy.get('rationale', '')
            })
        
        # Create LLM prompt for coverage validation
        validation_prompt = f"""Validate if this patent search has achieved comprehensive prior art coverage for the invention.

INVENTION CONTEXT:
Title: {invention_title}
Technology: {tech_description}
Applications: {tech_applications}
Key Technologies: {keywords}

SEARCH STRATEGIES EXECUTED ({len(search_strategies_used)}):
{chr(10).join(f"- {s['type']}: {s['rationale']}" for s in strategies_summary)}

SEARCH RESULTS SUMMARY:
- Total patents collected: {total_patents}
- Unique assignees: {len(unique_assignees)}
- Patent types: {', '.join(f"{k}({v})" for k, v in patent_types.items())}
- Date range: {date_range['earliest']} to {date_range['latest']}
- Average citations: {avg_citations:.1f}

SAMPLE PATENT TITLES (first 10):
{chr(10).join(f"- {p.get('patent_title', 'Unknown')}" for p in all_patents[:10])}

COVERAGE VALIDATION TASK:
Assess if the search has comprehensively covered all relevant prior art areas for this invention.

COVERAGE CRITERIA:
1. Technology Aspects: Are all core technology components covered?
2. Application Domains: Are all application areas explored?
3. Temporal Coverage: Both recent developments and historical foundational patents?
4. Assignee Diversity: Multiple organizations, not dominated by single entity?
5. Patent Type Coverage: Appropriate mix of utility, design, etc.?
6. Search Strategy Diversity: Multiple search approaches used?

GAPS TO IDENTIFY:
- Missing technology aspects not covered by current results
- Underrepresented application domains
- Temporal gaps (e.g., only old or only new patents)
- Missing key players in the field
- Alternative terminology not explored

RESPOND IN JSON FORMAT:
{{
    "coverage_completeness": 0.0-1.0,
    "missing_areas": ["list of specific gaps or areas not covered"],
    "additional_searches_needed": ["suggested specific search queries to fill gaps"],
    "search_termination_recommendation": "continue|sufficient|excellent",
    "coverage_analysis": "detailed explanation of coverage assessment",
    "strengths": ["list of well-covered areas"],
    "weaknesses": ["list of poorly-covered areas"]
}}"""

        try:
            bedrock_client = boto3.client('bedrock-runtime', region_name=AWS_REGION)
            request_body = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 1500,
                "messages": [{"role": "user", "content": validation_prompt}]
            }
            
            response = bedrock_client.invoke_model(
                modelId="us.anthropic.claude-3-7-sonnet-20250219-v1:0",
                body=json.dumps(request_body)
            )
            
            response_body = json.loads(response['body'].read())
            llm_response = response_body['content'][0]['text']
            
            # Parse JSON
            json_start = llm_response.find('{')
            json_end = llm_response.rfind('}') + 1
            if json_start != -1 and json_end != -1:
                json_str = llm_response[json_start:json_end]
                coverage_validation = json.loads(json_str)
                
                print(f"✅ Coverage validation: {coverage_validation['coverage_completeness']:.2f} completeness, recommendation: {coverage_validation['search_termination_recommendation']}")
                return coverage_validation
                
        except Exception as e:
            print(f"LLM coverage validation failed: {e}")
            # Fallback to simple validation
            return {
                'coverage_completeness': 0.7 if total_patents >= 20 else 0.5,
                'missing_areas': [],
                'additional_searches_needed': [],
                'search_termination_recommendation': 'sufficient' if total_patents >= 20 else 'continue',
                'coverage_analysis': f'Fallback validation: {total_patents} patents collected',
                'strengths': [f'{total_patents} patents found'],
                'weaknesses': ['LLM validation unavailable']
            }
            
    except Exception as e:
        print(f"Error validating search coverage: {e}")
        return {
            'coverage_completeness': 0.5,
            'missing_areas': [],
            'additional_searches_needed': [],
            'search_termination_recommendation': 'sufficient',
            'coverage_analysis': f'Validation error: {str(e)}',
            'strengths': [],
            'weaknesses': ['Validation failed']
        }

@tool
def generate_gap_filling_searches_llm(coverage_validation: Dict[str, Any], invention_context: Dict[str, Any], existing_strategies: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Generate additional search strategies to fill identified coverage gaps."""
    try:
        missing_areas = coverage_validation.get('missing_areas', [])
        additional_searches = coverage_validation.get('additional_searches_needed', [])
        
        if not missing_areas and not additional_searches:
            print("No coverage gaps identified, no additional searches needed")
            return []
        
        # Extract invention context
        invention_title = invention_context.get('title', '')
        tech_description = invention_context.get('technology_description', '')
        keywords = invention_context.get('keywords', '')
        
        # Summarize existing strategies
        existing_types = [s.get('strategy_type', 'unknown') for s in existing_strategies]
        
        gap_filling_prompt = f"""Generate targeted patent search strategies to fill identified coverage gaps.

INVENTION CONTEXT:
Title: {invention_title}
Technology: {tech_description}
Keywords: {keywords}

EXISTING SEARCH STRATEGIES USED:
{', '.join(existing_types)}

IDENTIFIED COVERAGE GAPS:
{chr(10).join(f"- {gap}" for gap in missing_areas)}

SUGGESTED ADDITIONAL SEARCHES:
{chr(10).join(f"- {search}" for search in additional_searches)}

TASK:
Generate 2-4 highly targeted PatentView search strategies that specifically address these gaps.

PATENTVIEW QUERY SYNTAX:
- Text operators: _text_any, _text_all, _text_phrase
- Fields: patent_title, patent_abstract
- Logical: _and, _or, _not
- Example: {{"_text_any": {{"patent_title": "machine learning"}}}}

FOCUS ON:
1. Alternative terminology for missed technology aspects
2. Specific application domains not yet covered
3. Temporal adjustments (older foundational patents or newer developments)
4. Specific assignees or inventors known in the field
5. Related but not identical technologies

RESPOND IN JSON FORMAT (2-4 strategies):
[
    {{
        "query_json": {{"_text_any": {{"patent_title": "gap-filling query"}}}},
        "strategy_type": "gap_filling_[specific_gap]",
        "rationale": "Addresses specific gap: [explanation]",
        "expected_relevance": "high|medium|low",
        "search_scope": "broad|medium|narrow"
    }}
]"""

        try:
            bedrock_client = boto3.client('bedrock-runtime', region_name=AWS_REGION)
            request_body = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 2000,
                "messages": [{"role": "user", "content": gap_filling_prompt}]
            }
            
            response = bedrock_client.invoke_model(
                modelId="us.anthropic.claude-3-7-sonnet-20250219-v1:0",
                body=json.dumps(request_body)
            )
            
            response_body = json.loads(response['body'].read())
            llm_response = response_body['content'][0]['text']
            
            # Parse JSON
            json_start = llm_response.find('[')
            json_end = llm_response.rfind(']') + 1
            if json_start != -1 and json_end != -1:
                json_str = llm_response[json_start:json_end]
                gap_strategies = json.loads(json_str)
                
                # Validate each strategy
                validated_strategies = []
                for strategy in gap_strategies:
                    if validate_patentview_query(strategy.get('query_json', {})):
                        validated_strategies.append(strategy)
                    else:
                        print(f"Invalid gap-filling query: {strategy}")
                
                print(f"✅ Generated {len(validated_strategies)} gap-filling search strategies")
                return validated_strategies
                
        except Exception as e:
            print(f"LLM gap-filling strategy generation failed: {e}")
            return []
            
    except Exception as e:
        print(f"Error generating gap-filling searches: {e}")
        return []

@tool
def store_patentview_analysis(pdf_filename: str, patent_data: Dict[str, Any]) -> str:
    """Store comprehensive PatentView patent analysis result with LLM evaluation in DynamoDB."""
    try:
        # Use patent_id as sort key
        sort_key = patent_data.get('patent_id') or patent_data.get('patent_number', 'unknown')
        
        # CRITICAL VALIDATION: Ensure patent has been evaluated by LLM
        llm_evaluation = patent_data.get('llm_evaluation', {})
        overall_relevance = llm_evaluation.get('overall_relevance_score', patent_data.get('relevance_score', 0.0))
        
        if overall_relevance == 0.0 and not llm_evaluation:
            return f"❌ REJECTED: Patent {sort_key} has not been evaluated by LLM. relevance_score=0, no llm_evaluation data. Must evaluate before storing."
        
        dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
        table = dynamodb.Table(RESULTS_TABLE)
        
        timestamp = datetime.utcnow().isoformat()
        
        # Helper function to handle empty values
        def get_value_or_na(value):
            return value if value else "N/A"
        
        # Process inventor names
        inventor_names = patent_data.get('inventor_names', [])
        inventors_str = '; '.join(inventor_names) if inventor_names else "N/A"
        
        # Process assignee names
        assignee_names = patent_data.get('assignee_names', [])
        assignees_str = '; '.join(assignee_names) if assignee_names else "N/A"
        
        # Extract LLM evaluation data
        technical_overlap = llm_evaluation.get('technical_overlap_score', 0.0)
        novelty_threat = llm_evaluation.get('novelty_threat_level', 'unknown')
        specific_overlaps = llm_evaluation.get('specific_overlaps', [])
        key_differences = llm_evaluation.get('key_differences', [])
        examiner_notes = llm_evaluation.get('examiner_notes', '')
        citation_recommendation = llm_evaluation.get('citation_recommendation', 'not_assessed')
        confidence_level = llm_evaluation.get('confidence_level', 'unknown')
        
        item = {
            # Primary Keys
            'pdf_filename': pdf_filename,
            'patent_number': sort_key,
            
            # Core Identity
            'patent_title': get_value_or_na(patent_data.get('patent_title', '')),
            'patent_abstract': get_value_or_na(patent_data.get('patent_abstract', '')),
            
            # Legal Status & Dates (Critical for novelty)
            'patent_type': get_value_or_na(patent_data.get('patent_type', '')),
            'grant_date': get_value_or_na(patent_data.get('patent_date', '')),
            'filing_date': get_value_or_na(patent_data.get('patent_date', '')),
            'publication_date': get_value_or_na(patent_data.get('patent_date', '')),
            
            # Ownership
            'patent_inventors': inventors_str,
            'patent_assignees': assignees_str,
            
            # Citation Information (Important for novelty assessment)
            'citation_count': patent_data.get('citation_count', 0),
            'times_cited': patent_data.get('citation_count', 0),
            
            # LLM-Powered Relevance Assessment
            'relevance_score': Decimal(str(overall_relevance)),
            'technical_overlap_score': Decimal(str(technical_overlap)),
            'novelty_threat_level': novelty_threat,
            'specific_overlaps': ', '.join(specific_overlaps) if specific_overlaps else 'None identified',
            'key_differences': ', '.join(key_differences) if key_differences else 'None identified',
            'llm_examiner_notes': examiner_notes,
            'citation_recommendation': citation_recommendation,
            'llm_confidence_level': confidence_level,
            
            # Search Metadata
            'search_strategy_type': get_value_or_na(patent_data.get('search_strategy_type', '')),
            'search_strategy_used': get_value_or_na(patent_data.get('search_query_used', '')),
            'search_timestamp': timestamp,
            'matching_keywords': get_value_or_na(patent_data.get('matching_keywords', '')),
            'data_source': get_value_or_na(patent_data.get('data_source', 'PatentView')),
            
            # PatentView URLs for reference
            'patentview_url': f"https://search.patentsview.org/api/v1/patent/?q={{\"patent_id\":\"{sort_key}\"}}",
            'google_patents_url': f"https://patents.google.com/patent/US{sort_key}",
            
            # Processing metadata
            'rank_position': 1,
            'application_status': 'Granted',  # PatentView only has granted patents
            
            # Legacy compatibility fields (set to N/A for PatentView)
            'specification_url': 'N/A',
            'abstract_url': 'N/A', 
            'claims_url': 'N/A',
            'specification_pages': 0,
            'abstract_pages': 0,
            'claims_pages': 0,
            'parent_patents': 0,
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

# PatentView Search Agent - LLM-Powered Optimized
patentview_search_agent = Agent(
    model="us.anthropic.claude-3-7-sonnet-20250219-v1:0",
    tools=[read_keywords_from_dynamodb, generate_patent_search_strategies_llm, execute_adaptive_patent_search, get_patentview_patent_details, evaluate_patent_relevance_llm, store_patentview_analysis],
    system_prompt="""You are an AI Patent Search Expert with advanced LLM capabilities for dynamic prior art discovery.

MISSION: Conduct comprehensive, adaptive patent searches using LLM intelligence for optimal prior art discovery and semantic relevance assessment.

WORKFLOW - OPTIMIZED SINGLE-ROUND SEARCH:

1. STRATEGIC PLANNING: 
   - Read patent analysis data from DynamoDB using the PDF filename
   - Use generate_patent_search_strategies_llm to create 3-4 intelligent search strategies based on invention analysis

2. ADAPTIVE EXECUTION: 
   - Execute each strategy using execute_adaptive_patent_search (includes automatic quality assessment and refinement)
   - Each search automatically refines queries if results are poor quality (max 1 refinement per search)
   - Collect all patents from all search strategies
   - Monitor search quality and results diversity

3. INTELLIGENT EVALUATION: 
   - Pre-filter: Select top 15 patents by citation count (focuses on most impactful prior art)
   - Use evaluate_patent_relevance_llm for semantic analysis of top 15 candidates only
   - LLM evaluates: technical overlap, novelty threat, specific overlaps, key differences
   - For patents with relevance > 0.6, get additional details using get_patentview_patent_details
   - Rank evaluated patents by LLM-determined relevance score

4. OPTIMAL SELECTION:
   - Select the top 6 most relevant patents across ALL search strategies
   - Prioritize patents with high novelty threat levels (high > medium > low)
   - Ensure diversity in patent types, assignees, and technical approaches
   - Store each selected patent with complete LLM evaluation using store_patentview_analysis

EXAMPLE WORKFLOW:
```
# 1. Get invention context
keywords_data = read_keywords_from_dynamodb(pdf_filename)

# 2. Generate LLM-powered search strategies (3-4 strategies)
strategies = generate_patent_search_strategies_llm(keywords_data)

# 3. Execute each strategy with adaptive refinement (max 1 refinement)
all_patents = []
for strategy in strategies:
    result = execute_adaptive_patent_search(strategy, keywords_data, limit=100, max_refinements=1)
    if result.get('success'):
        all_patents.extend(result['patents'])

# 4. Remove duplicates
unique_patents = {}
for patent in all_patents:
    patent_id = patent.get('patent_id')
    if patent_id and patent_id not in unique_patents:
        unique_patents[patent_id] = patent

all_patents = list(unique_patents.values())

# 5. Pre-filter: Select top 15 patents by citation count for LLM evaluation
# This reduces LLM calls while focusing on most impactful prior art
top_candidates = sorted(all_patents, key=lambda x: x.get('citation_count', 0), reverse=True)[:15]

# 6. LLM evaluation for top candidates only
for patent in top_candidates:
    # Use LLM for semantic relevance evaluation
    llm_eval = evaluate_patent_relevance_llm(patent, keywords_data)
    patent['llm_evaluation'] = llm_eval
    patent['relevance_score'] = llm_eval['overall_relevance_score']
    
    # Get details for high-relevance patents
    if llm_eval['overall_relevance_score'] > 0.6:
        details = get_patentview_patent_details(patent['patent_id'])
        if 'detailed_data' in details:
            patent.update(details['detailed_data'])

# 7. Select top 6 by LLM relevance and store
top_patents = sorted(top_candidates, key=lambda x: x.get('relevance_score', 0), reverse=True)[:6]
for patent in top_patents:
    store_patentview_analysis(pdf_filename, patent)
```

QUALITY STANDARDS:
- Zero tolerance for missed critical prior art
- LLM-powered semantic relevance assessment for maximum precision
- Complete coverage of technology landscape
- LLM-driven strategy generation for optimal query construction
- Deep semantic understanding over simple keyword matching
- Detailed examiner notes for each patent evaluation

CRITICAL RULES:
- Use LLM to generate EXACTLY 3 strategic search queries (optimized for speed)
- Execute ALL 3 generated strategies with adaptive refinement
- Each search automatically assesses quality and refines if needed (max 1 refinement per strategy)
- If a search returns 0 results, try the next strategy - DO NOT keep retrying the same failed query
- Remove duplicate patents before evaluation
- Pre-filter to top 15 patents by citation count (most impactful prior art)
- Use LLM to evaluate relevance for top 15 candidates only (reduces execution time)
- Select EXACTLY 6 most relevant patents for storage
- Prioritize patents with high novelty threat levels
- Store complete LLM evaluation data (overlaps, differences, examiner notes)
- MUST complete storage step - do not stop after evaluation
- NEVER store patents without LLM evaluation - relevance_score must be > 0

Execute with optimized LLM intelligence for speed and reliability:
1. LLM for strategic query generation (3-4 queries)
2. Rule-based search quality assessment (fast)
3. LLM for query refinement only when needed (max 1 per search)
4. LLM for semantic relevance evaluation (all unique patents)

This ensures efficient prior art discovery with automatic quality control and detailed novelty impact assessment while maintaining fast execution times."""
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
                if tool_name in ["generate_patent_search_strategies_llm", "execute_adaptive_patent_search"]:
                    search_metadata["strategies_used"].append(tool_name)
            elif "error" in event:
                yield {"error": event["error"]}
                return
        
        if full_response.strip():
            yield {"response": full_response, "search_metadata": search_metadata, "agent": "patentview_search"}
        else:
            yield {"error": "No response generated from PatentView search agent"}
                
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