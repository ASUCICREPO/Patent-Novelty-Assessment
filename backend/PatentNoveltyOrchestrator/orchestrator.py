#!/usr/bin/env python3
"""
Patent Novelty Orchestrator Agent.
Combines Keyword Generator and USPTO Search agents into a single orchestrator.
Routes requests to appropriate agents based on action type.
"""

import json
import os
import boto3
import requests
import re
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

# Gateway Configuration for USPTO Search
CLIENT_ID = os.environ.get('GATEWAY_CLIENT_ID')
CLIENT_SECRET = os.environ.get('GATEWAY_CLIENT_SECRET')
TOKEN_URL = os.environ.get('GATEWAY_TOKEN_URL')
GATEWAY_URL = os.environ.get('GATEWAY_URL')

# Gateway Configuration for Crossref Search
CROSSREF_CLIENT_ID = os.environ.get('CROSSREF_CLIENT_ID')
CROSSREF_CLIENT_SECRET = os.environ.get('CROSSREF_CLIENT_SECRET')
CROSSREF_TOKEN_URL = os.environ.get('CROSSREF_TOKEN_URL')
CROSSREF_GATEWAY_URL = os.environ.get('CROSSREF_GATEWAY_URL')

# Validate Gateway environment variables
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
    print(f"WARNING: Missing USPTO environment variables: {', '.join(missing_vars)}. USPTO search will fail.")

# Validate Crossref Gateway environment variables
crossref_missing_vars = []
if not CROSSREF_CLIENT_ID:
    crossref_missing_vars.append('CROSSREF_CLIENT_ID')
if not CROSSREF_CLIENT_SECRET:
    crossref_missing_vars.append('CROSSREF_CLIENT_SECRET')
if not CROSSREF_TOKEN_URL:
    crossref_missing_vars.append('CROSSREF_TOKEN_URL')
if not CROSSREF_GATEWAY_URL:
    crossref_missing_vars.append('CROSSREF_GATEWAY_URL')

if crossref_missing_vars:
    print(f"WARNING: Missing Crossref environment variables: {', '.join(crossref_missing_vars)}. Crossref search will fail.")

# =============================================================================
# KEYWORD GENERATOR TOOLS
# =============================================================================

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

def fetch_access_token():
    """Get OAuth access token for USPTO Gateway."""
    try:
        if not all([CLIENT_ID, CLIENT_SECRET, TOKEN_URL]):
            raise Exception("Missing required environment variables: GATEWAY_CLIENT_ID, GATEWAY_CLIENT_SECRET, GATEWAY_TOKEN_URL")
            
        print(f"Fetching USPTO token from: {TOKEN_URL}")
        print(f"USPTO Client ID: {CLIENT_ID}")
        
        response = requests.post(
            TOKEN_URL,
            data=f"grant_type=client_credentials&client_id={CLIENT_ID}&client_secret={CLIENT_SECRET}",
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            timeout=30
        )
        
        print(f"USPTO token response status: {response.status_code}")
        
        if response.status_code != 200:
            raise Exception(f"USPTO token request failed: {response.status_code} - {response.text}")
        
        token_data = response.json()
        access_token = token_data.get('access_token')
        
        if not access_token:
            raise Exception(f"No access token in USPTO response: {token_data}")
        
        return access_token
        
    except Exception as e:
        print(f"Error fetching USPTO access token: {e}")
        raise

def fetch_crossref_access_token():
    """Get OAuth access token for Crossref Gateway using your exact method."""
    try:
        if not all([CROSSREF_CLIENT_ID, CROSSREF_CLIENT_SECRET, CROSSREF_TOKEN_URL]):
            raise Exception("Missing required environment variables: CROSSREF_CLIENT_ID, CROSSREF_CLIENT_SECRET, CROSSREF_TOKEN_URL")
            
        print(f"Fetching Crossref token from: {CROSSREF_TOKEN_URL}")
        print(f"Crossref Client ID: {CROSSREF_CLIENT_ID}")
        
        # Use your exact method from the invocation code
        response = requests.post(
            CROSSREF_TOKEN_URL,
            data="grant_type=client_credentials&client_id={client_id}&client_secret={client_secret}".format(
                client_id=CROSSREF_CLIENT_ID, 
                client_secret=CROSSREF_CLIENT_SECRET
            ),
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            timeout=30
        )
        
        print(f"Crossref token response status: {response.status_code}")
        
        if response.status_code != 200:
            raise Exception(f"Crossref token request failed: {response.status_code} - {response.text}")
        
        token_data = response.json()
        access_token = token_data.get('access_token')
        
        if not access_token:
            raise Exception(f"No access token in Crossref response: {token_data}")
        
        return access_token
        
    except Exception as e:
        print(f"Error fetching Crossref access token: {e}")
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
                            
                            # Pre-process patents to extract relevant novelty assessment data
                            processed_patents = []
                            for patent in patents:
                                app_meta = patent.get('applicationMetaData', {})
                                
                                # Extract publication date from array (first element)
                                pub_date_bag = app_meta.get('publicationDateBag', [])
                                publication_date = pub_date_bag[0] if pub_date_bag else app_meta.get('earliestPublicationDate', '')
                                
                                # Extract inventor names properly
                                inventor_bag = app_meta.get('inventorBag', [])
                                inventor_names = []
                                for inventor in inventor_bag:
                                    # Try inventorNameText first, then construct from firstName/lastName
                                    name = inventor.get('inventorNameText', '')
                                    if not name:
                                        first = inventor.get('firstName', '')
                                        last = inventor.get('lastName', '')
                                        if first or last:
                                            name = f"{first} {last}".strip()
                                    if name:
                                        inventor_names.append(name)
                                
                                # Extract essential patent data for novelty assessment
                                processed_patent = {
                                    # Core Identity
                                    'applicationNumberText': patent.get('applicationNumberText', 'unknown'),
                                    'patentNumber': app_meta.get('patentNumber', ''),
                                    'inventionTitle': app_meta.get('inventionTitle', ''),
                                    
                                    # Legal Status & Dates
                                    'applicationStatusDescriptionText': app_meta.get('applicationStatusDescriptionText', ''),
                                    'filingDate': app_meta.get('filingDate', ''),
                                    'grantDate': app_meta.get('grantDate', ''),
                                    'publicationDate': publication_date,
                                    
                                    # Publication Info
                                    'earliestPublicationNumber': app_meta.get('earliestPublicationNumber', ''),
                                    
                                    # Inventor Data (processed)
                                    'inventorNames': inventor_names,
                                    
                                    # Parent Patent Info
                                    'parentContinuityBag': app_meta.get('parentContinuityBag', []),
                                    
                                    # Search metadata
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
def get_patent_documents(application_number: str) -> Dict[str, Any]:
    """Get patent documents (SPEC, ABST, CLM) for a specific application number."""
    try:
        # Get access token (reuse existing function)
        access_token = fetch_access_token()
        print(f"Getting documents for application: {application_number}")
        
        # Create MCP client using existing pattern
        mcp_client = MCPClient(lambda: create_streamable_http_transport(GATEWAY_URL, access_token))
        
        with mcp_client:
            # Get tools with pagination
            tools = get_full_tools_list(mcp_client)
            
            # Find document retrieval tool
            doc_tool = None
            for tool in tools:
                if 'getPatentDocuments' in tool.tool_name:
                    doc_tool = tool
                    break
            
            if not doc_tool:
                print("No document retrieval tool found")
                return {"error": "Document retrieval tool not available"}
            
            print(f"Using document tool: {doc_tool.tool_name}")
            
            # Call the document retrieval tool
            result = mcp_client.call_tool_sync(
                name=doc_tool.tool_name,
                arguments={"applicationNumber": application_number},
                tool_use_id=f"docs-{hash(application_number)}"
            )
            
            if result and isinstance(result, dict) and 'content' in result:
                content = result['content']
                if isinstance(content, list) and len(content) > 0:
                    text_content = content[0].get('text', '') if isinstance(content[0], dict) else str(content[0])
                    
                    try:
                        data = json.loads(text_content)
                        document_bag = data.get("documentBag", [])
                        
                        # Find target documents (SPEC, ABST, CLM)
                        target_docs = {'SPEC': None, 'ABST': None, 'CLM': None}
                        
                        for doc in document_bag:
                            doc_code = doc.get('documentCode', '')
                            official_date = doc.get('officialDate', '')
                            
                            # Check if this is a target document
                            if doc_code in target_docs:
                                # Keep the most recent version (latest official date)
                                if target_docs[doc_code] is None or official_date > target_docs[doc_code].get('officialDate', ''):
                                    target_docs[doc_code] = doc
                        
                        # Extract download URLs for each target document
                        document_urls = {}
                        for doc_type, doc_data in target_docs.items():
                            if doc_data:
                                download_options = doc_data.get('downloadOptionBag', [])
                                # Prefer PDF format
                                pdf_url = None
                                for option in download_options:
                                    if option.get('mimeTypeIdentifier') == 'PDF':
                                        pdf_url = option.get('downloadUrl')
                                        break
                                
                                if pdf_url:
                                    document_urls[doc_type.lower()] = {
                                        'url': pdf_url,
                                        'pages': option.get('pageTotalQuantity', 0),
                                        'official_date': doc_data.get('officialDate', ''),
                                        'document_id': doc_data.get('documentIdentifier', '')
                                    }
                                else:
                                    document_urls[doc_type.lower()] = None
                            else:
                                document_urls[doc_type.lower()] = None
                        
                        print(f"✅ Found documents for {application_number}: {list(document_urls.keys())}")
                        return {
                            "application_number": application_number,
                            "documents": document_urls,
                            "total_documents_found": len(document_bag)
                        }
                        
                    except json.JSONDecodeError as je:
                        print(f"JSON decode error in document retrieval: {je}")
                        return {"error": f"Failed to parse document response: {str(je)}"}
                else:
                    print("No content in document result")
                    return {"error": "No content in document response"}
            else:
                print(f"No content in document result: {result}")
                return {"error": "No valid document response"}
                
    except Exception as e:
        print(f"Error getting patent documents: {e}")
        import traceback
        traceback.print_exc()
        return {"error": f"Document retrieval failed: {str(e)}"}

@tool
def calculate_relevance_score(patent_data: Dict, original_keywords: Dict) -> float:
    """Calculate relevance score between patent and keywords."""
    try:
        # Combine patent text fields for matching (prioritize title and abstract)
        patent_text_parts = []
        
        # Title is most important
        title = patent_data.get('inventionTitle', '')
        if title:
            patent_text_parts.append(title)
        
        # Abstract is very important for novelty assessment
        abstract = patent_data.get('abstract', '')
        if abstract:
            patent_text_parts.append(abstract)
        
        # Claims are critical but may not be available in search results
        claims = patent_data.get('claims', '')
        if claims:
            patent_text_parts.append(claims)
        
        # Classification can also be relevant
        cpc_classes = patent_data.get('cpcClassificationBag', [])
        if cpc_classes:
            patent_text_parts.append(' '.join(cpc_classes))
        
        patent_text = ' '.join(patent_text_parts).lower()
        
        # Get the keywords string and split into individual keywords
        keywords_string = original_keywords.get('keywords', '')
        if not keywords_string:
            return 0.0
        
        keyword_list = [k.strip().lower() for k in keywords_string.split(',') if k.strip()]
        if not keyword_list:
            return 0.0
        
        # Count matches
        matches = sum(1 for keyword in keyword_list if keyword in patent_text)
        
        # Calculate base score as percentage of keywords found
        base_score = matches / len(keyword_list)
        
        # Bonus scoring for different fields
        title_lower = title.lower()
        abstract_lower = abstract.lower()
        
        # Title matches get highest bonus (30%)
        title_matches = sum(1 for keyword in keyword_list if keyword in title_lower)
        if title_matches > 0:
            base_score += (title_matches / len(keyword_list)) * 0.3
        
        # Abstract matches get medium bonus (20%)
        abstract_matches = sum(1 for keyword in keyword_list if keyword in abstract_lower)
        if abstract_matches > 0:
            base_score += (abstract_matches / len(keyword_list)) * 0.2
        
        # Bonus for granted patents (more relevant for novelty)
        status = patent_data.get('applicationStatusDescriptionText', '').lower()
        if 'patented case' in status or 'granted' in status:
            base_score += 0.1
        
        return round(min(base_score, 1.0), 3)  # Cap at 1.0
        
    except Exception as e:
        print(f"Error calculating relevance score: {str(e)}")
        return 0.0

@tool
def store_patent_analysis(pdf_filename: str, patent_data: Dict[str, Any]) -> str:
    """Store comprehensive patent analysis result in DynamoDB."""
    try:
        dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
        table = dynamodb.Table(RESULTS_TABLE)
        
        timestamp = datetime.utcnow().isoformat()
        
        # Use patent number as sort key, fallback to application number
        sort_key = patent_data.get('patentNumber') or patent_data.get('applicationNumberText', 'unknown')
        
        # Helper function to handle empty values
        def get_value_or_na(value):
            return value if value else "N/A"
        
        # Process inventor names
        inventor_names = patent_data.get('inventorNames', [])
        inventors_str = '; '.join(inventor_names) if inventor_names else "N/A"
        
        item = {
            # Primary Keys
            'pdf_filename': pdf_filename,
            'patent_number': sort_key,
            
            # Core Identity
            'patent_title': get_value_or_na(patent_data.get('inventionTitle', '')),
            
            # Legal Status & Dates (Critical for novelty)
            'application_status': get_value_or_na(patent_data.get('applicationStatusDescriptionText', '')),
            'filing_date': get_value_or_na(patent_data.get('filingDate', '')),
            'publication_date': get_value_or_na(patent_data.get('publicationDate', '')),
            
            # Ownership
            'patent_inventors': inventors_str,
            
            # Secondary Info
            'publication_number': get_value_or_na(patent_data.get('earliestPublicationNumber', '')),
            'parent_patents': patent_data.get('parentContinuityBag', []) and len(patent_data.get('parentContinuityBag', [])) or 0,
            
            # Search Metadata
            'relevance_score': Decimal(str(patent_data.get('relevance_score', 0.0))),
            'search_strategy_used': get_value_or_na(patent_data.get('search_query_used', '')),
            'search_timestamp': timestamp,
            'matching_keywords': get_value_or_na(patent_data.get('matching_keywords', '')),
            
            # Document URLs (NEW)
            'specification_url': get_value_or_na(patent_data.get('documents', {}).get('spec', {}).get('url', '') if patent_data.get('documents', {}).get('spec') else ''),
            'abstract_url': get_value_or_na(patent_data.get('documents', {}).get('abst', {}).get('url', '') if patent_data.get('documents', {}).get('abst') else ''),
            'claims_url': get_value_or_na(patent_data.get('documents', {}).get('clm', {}).get('url', '') if patent_data.get('documents', {}).get('clm') else ''),
            
            # Document Metadata (NEW)
            'specification_pages': patent_data.get('documents', {}).get('spec', {}).get('pages', 0) if patent_data.get('documents', {}).get('spec') else 0,
            'abstract_pages': patent_data.get('documents', {}).get('abst', {}).get('pages', 0) if patent_data.get('documents', {}).get('abst') else 0,
            'claims_pages': patent_data.get('documents', {}).get('clm', {}).get('pages', 0) if patent_data.get('documents', {}).get('clm') else 0,
            
            # URLs for reference
            'uspto_url': f"https://patents.uspto.gov/patent/{sort_key}",
            
            # Processing metadata
            'rank_position': 1
        }
        
        # Put item in DynamoDB
        table.put_item(Item=item)
        
        patent_title = patent_data.get('inventionTitle', 'Unknown Title')
        return f"Successfully stored patent {sort_key}: {patent_title}"
        
    except Exception as e:
        sort_key = patent_data.get('patentNumber') or patent_data.get('applicationNumberText', 'unknown')
        return f"Error storing patent {sort_key}: {str(e)}"

# =============================================================================
# SCHOLARLY ARTICLE SEARCH TOOLS
# =============================================================================

def run_crossref_search(search_query: str, limit: int = 25):
    """Run Crossref search using your exact invocation method."""
    try:
        access_token = fetch_crossref_access_token()
        mcp_client = MCPClient(lambda: create_streamable_http_transport(CROSSREF_GATEWAY_URL, access_token))
        
        with mcp_client:
            tools = get_full_tools_list(mcp_client)
            print(f"Found the following Crossref tools: {[tool.tool_name for tool in tools]}")
            
            # Find the Crossref-specific tool (following your pattern)
            if tools:
                # Look for the Crossref search tool specifically
                crossref_tool = None
                for tool in tools:
                    if 'crossref' in tool.tool_name.lower() or 'searchScholarlyWorks' in tool.tool_name:
                        crossref_tool = tool
                        break
                
                # Use Crossref tool if found, otherwise use first tool
                tool_name = crossref_tool.tool_name if crossref_tool else tools[0].tool_name
                print(f"Using Crossref tool: {tool_name}")
                
                # Call tool with arguments matching your OpenAPI spec
                result = mcp_client.call_tool_sync(
                    name=tool_name,
                    arguments={
                        "query": search_query,
                        "rows": limit,
                        "mailto": "narutouzumakihokage786@gmail.com"
                    },
                    tool_use_id=f"crossref-search-{hash(search_query)}"
                )
                return result
            else:
                print("No Crossref tools available")
                return None
                
    except Exception as e:
        print(f"Error in Crossref search: {e}")
        return None

@tool
def search_crossref_articles(search_query: str, limit: int = 25) -> List[Dict[str, Any]]:
    """Search scholarly articles via Crossref Gateway using your exact invocation method."""
    try:
        if not CROSSREF_GATEWAY_URL:
            print("❌ CROSSREF_GATEWAY_URL not configured")
            return []
        
        print(f"🔍 Searching Crossref for: {search_query}")
        
        # Use your exact invocation pattern
        result = run_crossref_search(search_query, limit)
        
        print(f"Crossref tool call result type: {type(result)}")
        
        if result and isinstance(result, dict) and 'content' in result:
            content = result['content']
            if isinstance(content, list) and len(content) > 0:
                text_content = content[0].get('text', '') if isinstance(content[0], dict) else str(content[0])
                print(f"Crossref content preview: {text_content[:200]}...")
                
                try:
                    data = json.loads(text_content)
                    articles = data.get("message", {}).get("items", [])
                    
                    if articles:
                        print(f"✅ Found {len(articles)} scholarly articles!")
                        
                        # Process articles to extract relevant information
                        processed_articles = []
                        for article in articles:
                            # Extract key information from Crossref response
                            processed_article = {
                                'DOI': article.get('DOI', 'unknown'),
                                'title': article.get('title', ['Unknown Title'])[0] if article.get('title') else 'Unknown Title',
                                'authors': extract_authors(article.get('author', [])),
                                'journal': article.get('container-title', ['Unknown Journal'])[0] if article.get('container-title') else 'Unknown Journal',
                                'published_date': extract_published_date(article.get('published')),
                                'abstract': article.get('abstract', ''),
                                'publisher': article.get('publisher', ''),
                                'url': article.get('URL', ''),
                                'citation_count': article.get('is-referenced-by-count', 0),
                                'type': article.get('type', 'journal-article'),
                                'subject': article.get('subject', []),
                                'search_query_used': search_query,
                                'relevance_score': 0.8,  # Default relevance score
                                'matching_keywords': search_query
                            }
                            processed_articles.append(processed_article)
                        
                        return processed_articles
                    else:
                        print(f"⚠️ No articles found in Crossref response")
                        return []
                        
                except json.JSONDecodeError as je:
                    print(f"JSON decode error in Crossref response: {je}")
                    return []
            else:
                print(f"No content in Crossref result: {result}")
                return []
                
    except Exception as e:
        print(f"Error searching Crossref: {e}")
        import traceback
        traceback.print_exc()
        return []

def extract_authors(authors_list: List[Dict]) -> str:
    """Extract author names from Crossref author list."""
    try:
        author_names = []
        for author in authors_list[:5]:  # Limit to first 5 authors
            given = author.get('given', '')
            family = author.get('family', '')
            if family:
                if given:
                    author_names.append(f"{family}, {given}")
                else:
                    author_names.append(family)
        
        if len(authors_list) > 5:
            author_names.append("et al.")
        
        return '; '.join(author_names) if author_names else 'Unknown Authors'
    except Exception:
        return 'Unknown Authors'

def extract_published_date(published_info: Dict) -> str:
    """Extract published date from Crossref date format."""
    try:
        if published_info and 'date-parts' in published_info:
            date_parts = published_info['date-parts'][0]
            if len(date_parts) >= 3:
                return f"{date_parts[0]}-{date_parts[1]:02d}-{date_parts[2]:02d}"
            elif len(date_parts) >= 2:
                return f"{date_parts[0]}-{date_parts[1]:02d}"
            elif len(date_parts) >= 1:
                return str(date_parts[0])
        return ''
    except Exception:
        return ''

@tool
def calculate_article_relevance_score(article_data: Dict, original_keywords: Dict) -> float:
    """Calculate relevance score between scholarly article and keywords."""
    try:
        # Combine article text fields for matching
        article_text = f"{article_data.get('title', '')} {article_data.get('abstract', '')} {article_data.get('journal', '')}"
        article_text_lower = article_text.lower()
        
        # Get the keywords string and split into individual keywords
        keywords_string = original_keywords.get('keywords', '')
        if not keywords_string:
            return 0.0
        
        keyword_list = [k.strip().lower() for k in keywords_string.split(',') if k.strip()]
        if not keyword_list:
            return 0.0
        
        # Count matches
        matches = sum(1 for keyword in keyword_list if keyword in article_text_lower)
        
        # Calculate score as percentage of keywords found
        score = matches / len(keyword_list)
        
        # Bonus for title matches (more important)
        title_lower = article_data.get('title', '').lower()
        title_matches = sum(1 for keyword in keyword_list if keyword in title_lower)
        if title_matches > 0:
            score += (title_matches / len(keyword_list)) * 0.2  # 20% bonus for title matches
        
        # Bonus for recent publications (articles from last 5 years get slight boost)
        try:
            pub_date = article_data.get('published_date', '')
            if pub_date and len(pub_date) >= 4:
                pub_year = int(pub_date[:4])
                current_year = datetime.utcnow().year
                if current_year - pub_year <= 5:
                    score += 0.05  # Small bonus for recent articles
        except:
            pass
        
        return round(min(score, 1.0), 3)  # Cap at 1.0
        
    except Exception as e:
        print(f"Error calculating article relevance score: {str(e)}")
        return 0.0

@tool
def store_article_analysis(pdf_filename: str, article_doi: str, article_title: str, authors: str, journal: str, 
                          published_date: str, relevance_score: float, search_query: str, citation_count: int = 0, 
                          article_url: str = '', publisher: str = '', article_type: str = '') -> str:
    """Store individual scholarly article analysis result in DynamoDB."""
    try:
        dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
        table = dynamodb.Table(ARTICLES_TABLE)
        
        timestamp = datetime.utcnow().isoformat()
        
        item = {
            'pdf_filename': pdf_filename,
            'article_doi': article_doi,
            'article_title': article_title,
            'authors': authors,
            'journal': journal,
            'published_date': published_date,
            'relevance_score': Decimal(str(relevance_score)),
            'search_strategy_used': search_query,
            'search_timestamp': timestamp,
            'article_url': article_url,
            'citation_count': citation_count,
            'publisher': publisher,
            'article_type': article_type,
            'matching_keywords': search_query,
            'rank_position': 1,
            'total_results_found': 1,
            'search_strategies_tried': [search_query]
        }
        
        table.put_item(Item=item)
        return f"Successfully stored article {article_doi}: {article_title}"
        
    except Exception as e:
        return f"Error storing article {article_doi}: {str(e)}"

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

# USPTO Search Agent
uspto_search_agent = Agent(
    model="us.anthropic.claude-3-7-sonnet-20250219-v1:0",
    tools=[read_keywords_from_dynamodb, search_uspto_patents, get_patent_documents, calculate_relevance_score, store_patent_analysis],
    system_prompt="""You are a USPTO Patent Search Expert. Execute this workflow EXACTLY ONCE:

    1. Read patent analysis data from DynamoDB using the PDF filename
    2. Use the extracted keywords to execute 2-3 strategic USPTO searches
    3. For each relevant patent found, get its documents (SPEC, ABST, CLM) using get_patent_documents
    4. Merge patent data with document URLs before storing
    5. Store comprehensive patent data including document URLs in DynamoDB

    CRITICAL DATA MERGING PROCESS:
    For each patent you want to store:
    1. Take the patent data from search_uspto_patents results
    2. Call get_patent_documents with the patent's applicationNumberText
    3. Add the 'documents' field from get_patent_documents to the patent data
    4. Call store_patent_analysis with the merged data structure

    EXAMPLE WORKFLOW:
    ```
    # Get patent from search results
    patent = search_results[0]  # e.g., has applicationNumberText, inventionTitle, etc.
    
    # Get documents for this patent
    docs = get_patent_documents(patent['applicationNumberText'])
    
    # Merge the data
    patent['documents'] = docs['documents']  # Add document URLs to patent data
    
    # Store the complete data
    store_patent_analysis(pdf_filename, patent)
    ```

    SEARCH STRATEGIES:
    Use the keywords from the patent analysis to create strategic searches:
    1. Core technical keywords (focus on mechanism/technology terms)
    2. Application domain keywords (focus on use case/application terms)
    3. Combined keyword search (mix technical + application terms)

    CRITICAL RULES:
    - Execute each tool call only once per search strategy
    - For each patent found, ALWAYS call get_patent_documents to get document URLs
    - ALWAYS merge patent data with document data before storing
    - If a search fails, continue with the next strategy
    - Maximum 3 search attempts total
    - Always store results even if searches fail
    - Do not retry failed searches

    Focus on patents that could impact novelty assessment - prioritize granted patents over applications."""
)

# Scholarly Article Search Agent
scholarly_article_agent = Agent(
    model="us.anthropic.claude-3-7-sonnet-20250219-v1:0",
    tools=[read_keywords_from_dynamodb, search_crossref_articles, calculate_article_relevance_score, store_article_analysis],
    system_prompt="""You are a Scholarly Article Search Expert. Execute this workflow EXACTLY ONCE:

    1. Read patent analysis data from DynamoDB using the PDF filename
    2. Use the extracted keywords to execute 2-3 strategic Crossref searches
    3. Score and select the top 5 most relevant scholarly articles
    4. Store results in DynamoDB

    CRITICAL RULES:
    - Execute each tool call only once per search strategy
    - If a search fails, continue with the next strategy
    - Maximum 3 search attempts total
    - Always store results even if searches fail
    - Do not retry failed searches

    SEARCH STRATEGIES:
    Use the keywords from the patent analysis to create strategic searches:
    1. Core technical keywords (focus on mechanism/technology terms)
    2. Application domain keywords (focus on use case/application terms)  
    3. Combined keyword search (mix technical + application terms)

    The keywords are provided as a comma-separated list. Select the most relevant terms for each search strategy.

    Focus on finding scholarly articles that discuss similar technologies, applications, or research areas that could provide academic context for the invention."""
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
            elif "current_tool_use" in event and event["current_tool_use"].get("name"):
                yield {"tool_name": event["current_tool_use"]["name"], "agent": "keyword_generator"}
            elif "error" in event:
                yield {"error": event["error"]}
                return
        
        # Yield the complete response once streaming is done
        if full_response.strip():
            yield {"response": full_response, "agent": "keyword_generator"}
        else:
            yield {"error": "No response generated from keyword generator agent"}
                
    except Exception as e:
        yield {"error": f"Error in keyword generation: {str(e)}"}

async def handle_uspto_search(payload):
    """Handle USPTO patent search requests."""
    print("🔍 Orchestrator: Routing to USPTO Search Agent")
    
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            payload = {"pdf_filename": payload}
    
    pdf_filename = payload.get("pdf_filename")
    
    if not pdf_filename:
        yield {"error": "Error: 'pdf_filename' is required for USPTO search."}
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
                yield {"tool_name": tool_name, "agent": "uspto_search"}
                if tool_name == "search_uspto_patents":
                    search_metadata["strategies_used"].append(tool_name)
            elif "error" in event:
                yield {"error": event["error"]}
                return
        
        if full_response.strip():
            yield {"response": full_response, "search_metadata": search_metadata, "agent": "uspto_search"}
        else:
            yield {"error": "No response generated from USPTO search agent"}
                
    except Exception as e:
        yield {"error": f"Error in USPTO search: {str(e)}"}

async def handle_scholarly_search(payload):
    """Handle scholarly article search requests."""
    print("🔍 Orchestrator: Routing to Scholarly Article Search Agent")
    
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            payload = {"pdf_filename": payload}
    
    pdf_filename = payload.get("pdf_filename")
    
    if not pdf_filename:
        yield {"error": "Error: 'pdf_filename' is required for scholarly article search."}
        return
    
    enhanced_prompt = f"""Search for scholarly articles related to the invention in PDF: {pdf_filename}

    INSTRUCTIONS:
    1. Read keywords from DynamoDB for this PDF
    2. Analyze the invention's technical and application aspects
    3. Execute multiple strategic Crossref searches via Gateway
    4. Score and rank results by relevance to the invention
    5. Select top 5 most relevant scholarly articles
    6. Store results with comprehensive metadata

    Focus on finding academic research that discusses similar technologies, methodologies, or applications that could provide scientific context for the patent novelty assessment."""
        
    try:
        full_response = ""
        search_metadata = {"strategies_used": [], "total_results": 0}
        
        async for event in scholarly_article_agent.stream_async(enhanced_prompt):
            if "data" in event:
                full_response += event["data"]
            elif "current_tool_use" in event and event["current_tool_use"].get("name"):
                tool_name = event["current_tool_use"]["name"]
                yield {"tool_name": tool_name, "agent": "scholarly_search"}
                if tool_name == "search_crossref_articles":
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
        async for event in handle_uspto_search(payload):
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