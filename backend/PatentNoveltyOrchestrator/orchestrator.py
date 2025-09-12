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
        table = dynamodb.Table(KEYWORDS_TABLE)
        
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
        
        return f"Successfully stored keywords for {pdf_filename} in DynamoDB table {KEYWORDS_TABLE}"
        
    except Exception as e:
        error_msg = f"Error storing keywords in DynamoDB: {str(e)}"
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
        score = 0.0
        total_weight = 0.0
        
        # Combine article text fields for matching
        article_text = f"{article_data.get('title', '')} {article_data.get('abstract', '')} {article_data.get('journal', '')}"
        article_text_lower = article_text.lower()
        
        # Weight different keyword categories for academic articles
        weights = {
            'mechanism_composition': 0.35,  # Technical terms are important
            'application_use': 0.35,        # Application context is important
            'synonyms': 0.20,               # Alternative terms help matching
            'patent_classifications': 0.10   # Less relevant for academic articles
        }
        
        for category, weight in weights.items():
            keywords = original_keywords.get(category, '')
            if keywords:
                keyword_list = [k.strip() for k in keywords.split(',') if k.strip()]
                matches = sum(1 for keyword in keyword_list if keyword.lower() in article_text_lower)
                category_score = min(matches / len(keyword_list), 1.0) if keyword_list else 0.0
                score += category_score * weight
                total_weight += weight
        
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
        
        return round(score / total_weight if total_weight > 0 else 0.0, 3)
        
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

# USPTO Search Agent
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

# Scholarly Article Search Agent
scholarly_article_agent = Agent(
    model="us.anthropic.claude-3-7-sonnet-20250219-v1:0",
    tools=[read_keywords_from_dynamodb, search_crossref_articles, calculate_article_relevance_score, store_article_analysis],
    system_prompt="""You are a Scholarly Article Search Expert. Execute this workflow EXACTLY ONCE:

1. Read keywords from DynamoDB using the PDF filename
2. Execute 2-3 strategic Crossref searches using different keyword combinations
3. Score and select the top 5 most relevant scholarly articles
4. Store results in DynamoDB

CRITICAL RULES:
- Execute each tool call only once per search strategy
- If a search fails, continue with the next strategy
- Maximum 3 search attempts total
- Always store results even if searches fail
- Do not retry failed searches

SEARCH STRATEGIES:
1. Core mechanism terms (e.g., "spiral stent", "medical device")
2. Application terms (e.g., "biliary intervention", "pancreatic stricture")
3. Combined technical + application terms

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