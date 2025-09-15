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
        patent_text = f"{patent_data.get('title', '')} {patent_data.get('abstract', '')}"
        patent_text_lower = patent_text.lower()
        
        # Get the keywords string and split into individual keywords
        keywords_string = original_keywords.get('keywords', '')
        if not keywords_string:
            return 0.0
        
        keyword_list = [k.strip().lower() for k in keywords_string.split(',') if k.strip()]
        if not keyword_list:
            return 0.0
        
        # Count matches
        matches = sum(1 for keyword in keyword_list if keyword in patent_text_lower)
        
        # Calculate score as percentage of keywords found
        score = matches / len(keyword_list)
        
        # Bonus for title matches (more important)
        title_lower = patent_data.get('title', '').lower()
        title_matches = sum(1 for keyword in keyword_list if keyword in title_lower)
        if title_matches > 0:
            score += (title_matches / len(keyword_list)) * 0.2  # 20% bonus for title matches
        
        return round(min(score, 1.0), 3)  # Cap at 1.0
        
    except Exception as e:
        print(f"Error calculating relevance score: {str(e)}")
        return 0.0

@tool
def analyze_patent_results_quality(
    patents: List[Dict], 
    original_keywords: Dict, 
    quality_threshold: float = 0.25,
    min_patents: int = 3
) -> Dict[str, Any]:
    """
    Analyze the quality of USPTO patent search results.
    
    Args:
        patents: List of patents from search
        original_keywords: Original invention keywords
        quality_threshold: Minimum average relevance score required
        min_patents: Minimum number of patents needed
    
    Returns:
        Quality analysis with recommendations
    """
    try:
        if not patents:
            return {
                "meets_threshold": False,
                "average_score": 0.0,
                "patent_count": 0,
                "quality_assessment": "No patents found",
                "recommendation": "try_different_strategy",
                "detailed_scores": []
            }
        
        # Calculate relevance scores for all patents
        scores = []
        detailed_analysis = []
        
        for patent in patents:
            score = calculate_relevance_score(patent, original_keywords)
            scores.append(score)
            
            # Extract patent metadata
            app_meta = patent.get('applicationMetaData', {})
            detailed_analysis.append({
                "patent_number": patent.get('applicationNumberText', 'Unknown'),
                "title": app_meta.get('inventionTitle', 'Unknown Title'),
                "relevance_score": score,
                "applicant": app_meta.get('applicantName', 'Unknown'),
                "filing_date": app_meta.get('filingDate', ''),
                "status": app_meta.get('applicationStatus', 'Unknown')
            })
        
        # Calculate quality metrics
        average_score = sum(scores) / len(scores) if scores else 0.0
        max_score = max(scores) if scores else 0.0
        high_quality_count = sum(1 for score in scores if score >= quality_threshold)
        
        # Filter patents that meet individual threshold
        qualifying_patents = [
            analysis for analysis in detailed_analysis 
            if analysis["relevance_score"] >= quality_threshold
        ]
        
        # Determine if we have enough qualifying patents
        meets_threshold = len(qualifying_patents) >= min_patents
        
        # Generate quality assessment based on individual patent thresholds
        if meets_threshold:
            quality_assessment = f"Success: {len(qualifying_patents)} patents meet {quality_threshold} threshold (need {min_patents})"
            recommendation = "accept_results"
        elif len(qualifying_patents) > 0:
            quality_assessment = f"Partial success: {len(qualifying_patents)} patents meet threshold, need {min_patents - len(qualifying_patents)} more"
            recommendation = "try_refined_strategy"
        else:
            quality_assessment = f"No qualifying patents: 0 patents meet {quality_threshold} threshold (highest: {max_score:.3f})"
            recommendation = "try_different_strategy"
        
        return {
            "meets_threshold": meets_threshold,
            "average_score": round(average_score, 3),
            "max_score": round(max_score, 3),
            "patent_count": len(patents),
            "qualifying_patents_count": len(qualifying_patents),
            "quality_assessment": quality_assessment,
            "recommendation": recommendation,
            "qualifying_patents": qualifying_patents,  # Patents that meet threshold
            "detailed_scores": detailed_analysis[:10]  # Top 10 for analysis
        }
        
    except Exception as e:
        return {
            "meets_threshold": False,
            "average_score": 0.0,
            "patent_count": 0,
            "quality_assessment": f"Error analyzing patent results: {str(e)}",
            "recommendation": "try_different_strategy",
            "detailed_scores": []
        }

@tool
def store_patent_analysis(pdf_filename: str, patent_number: str, patent_title: str, inventor: str, assignee: str, relevance_score: float, search_query: str, rank_position: int = 1) -> str:
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
            'rank_position': rank_position,
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



@tool
def advanced_crossref_search(
    query: str, 
    search_type: str = "simple",
    search_fields: str = "all", 
    use_boolean: bool = False,
    phrase_search: bool = False,
    limit: int = 25
) -> List[Dict[str, Any]]:
    """
    Advanced Crossref search with multiple search strategies and parameters.
    
    Args:
        query: Search query string
        search_type: "simple", "title_only", "abstract_focus", "author_focus", "journal_focus"
        search_fields: "all", "title", "abstract", "author", "journal" 
        use_boolean: Whether to treat query as boolean expression
        phrase_search: Whether to search for exact phrases
        limit: Maximum results to return
    
    Returns:
        List of processed articles with metadata
    """
    try:
        if not CROSSREF_GATEWAY_URL:
            print("❌ CROSSREF_GATEWAY_URL not configured")
            return []
        
        # Construct search parameters based on strategy
        search_params = {
            "query": query,
            "rows": limit,
            "mailto": "narutouzumakihokage786@gmail.com"
        }
        
        # Apply search type modifications
        if search_type == "title_only":
            search_params["query.title"] = query
            search_params.pop("query", None)
        elif search_type == "abstract_focus":
            search_params["query.abstract"] = query
            search_params.pop("query", None)
        elif search_type == "author_focus":
            search_params["query.author"] = query
            search_params.pop("query", None)
        elif search_type == "journal_focus":
            search_params["query.container-title"] = query
            search_params.pop("query", None)
        
        # Add phrase search handling
        if phrase_search and "query" in search_params:
            # Wrap phrases in quotes for exact matching
            if not query.startswith('"'):
                search_params["query"] = f'"{query}"'
        
        print(f"🔍 Advanced Crossref Search:")
        print(f"   Type: {search_type}")
        print(f"   Fields: {search_fields}")
        print(f"   Boolean: {use_boolean}")
        print(f"   Phrase: {phrase_search}")
        print(f"   Query: {query}")
        
        # Execute search using modified parameters
        result = run_crossref_search_advanced(search_params)
        
        if result and isinstance(result, dict) and 'content' in result:
            content = result['content']
            if isinstance(content, list) and len(content) > 0:
                text_content = content[0].get('text', '') if isinstance(content[0], dict) else str(content[0])
                
                try:
                    data = json.loads(text_content)
                    articles = data.get("message", {}).get("items", [])
                    
                    if articles:
                        print(f"✅ Found {len(articles)} articles with {search_type} strategy")
                        
                        # Process articles to extract relevant information
                        processed_articles = []
                        for article in articles:
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
                                'search_strategy': search_type,
                                'search_query_used': query,
                                'search_parameters': search_params
                            }
                            processed_articles.append(processed_article)
                        
                        return processed_articles
                    else:
                        print(f"⚠️ No articles found with {search_type} strategy")
                        return []
                        
                except json.JSONDecodeError as je:
                    print(f"JSON decode error: {je}")
                    return []
            else:
                print(f"No content in result")
                return []
                
    except Exception as e:
        print(f"Error in advanced Crossref search: {e}")
        import traceback
        traceback.print_exc()
        return []

def run_crossref_search_advanced(search_params: Dict):
    """Run Crossref search with advanced parameters."""
    try:
        access_token = fetch_crossref_access_token()
        mcp_client = MCPClient(lambda: create_streamable_http_transport(CROSSREF_GATEWAY_URL, access_token))
        
        with mcp_client:
            tools = get_full_tools_list(mcp_client)
            
            if tools:
                # Look for the Crossref search tool
                crossref_tool = None
                for tool in tools:
                    if 'crossref' in tool.tool_name.lower() or 'searchScholarlyWorks' in tool.tool_name:
                        crossref_tool = tool
                        break
                
                tool_name = crossref_tool.tool_name if crossref_tool else tools[0].tool_name
                
                # Call tool with advanced parameters
                result = mcp_client.call_tool_sync(
                    name=tool_name,
                    arguments=search_params,
                    tool_use_id=f"advanced-crossref-{hash(str(search_params))}"
                )
                return result
            else:
                print("No Crossref tools available")
                return None
                
    except Exception as e:
        print(f"Error in advanced Crossref search execution: {e}")
        return None

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
def analyze_search_results_quality(
    articles: List[Dict], 
    original_keywords: Dict, 
    quality_threshold: float = 0.3,
    min_articles: int = 3
) -> Dict[str, Any]:
    """
    Analyze the quality of search results and determine if they meet standards.
    
    Args:
        articles: List of articles from search
        original_keywords: Original invention keywords
        quality_threshold: Minimum average relevance score required
        min_articles: Minimum number of articles needed
    
    Returns:
        Quality analysis with recommendations
    """
    try:
        if not articles:
            return {
                "meets_threshold": False,
                "average_score": 0.0,
                "article_count": 0,
                "quality_assessment": "No articles found",
                "recommendation": "try_different_strategy",
                "detailed_scores": []
            }
        
        # Calculate relevance scores for all articles
        scores = []
        detailed_analysis = []
        
        for article in articles:
            score = calculate_article_relevance_score(article, original_keywords)
            scores.append(score)
            
            detailed_analysis.append({
                "title": article.get('title', 'Unknown'),
                "doi": article.get('DOI', 'unknown'),
                "relevance_score": score,
                "citation_count": article.get('citation_count', 0),
                "published_date": article.get('published_date', ''),
                "journal": article.get('journal', 'Unknown')
            })
        
        # Calculate quality metrics
        average_score = sum(scores) / len(scores) if scores else 0.0
        max_score = max(scores) if scores else 0.0
        high_quality_count = sum(1 for score in scores if score >= quality_threshold)
        
        # Filter articles that meet individual threshold
        qualifying_articles = [
            analysis for analysis in detailed_analysis 
            if analysis["relevance_score"] >= quality_threshold
        ]
        
        # Determine if we have enough qualifying articles
        meets_threshold = len(qualifying_articles) >= min_articles
        
        # Generate quality assessment based on individual article thresholds
        if meets_threshold:
            quality_assessment = f"Success: {len(qualifying_articles)} articles meet {quality_threshold} threshold (need {min_articles})"
            recommendation = "accept_results"
        elif len(qualifying_articles) > 0:
            quality_assessment = f"Partial success: {len(qualifying_articles)} articles meet threshold, need {min_articles - len(qualifying_articles)} more"
            recommendation = "try_refined_strategy"
        else:
            quality_assessment = f"No qualifying articles: 0 articles meet {quality_threshold} threshold (highest: {max_score:.3f})"
            recommendation = "try_different_strategy"
        
        return {
            "meets_threshold": meets_threshold,
            "average_score": round(average_score, 3),
            "max_score": round(max_score, 3),
            "article_count": len(articles),
            "qualifying_articles_count": len(qualifying_articles),
            "quality_assessment": quality_assessment,
            "recommendation": recommendation,
            "qualifying_articles": qualifying_articles,  # Articles that meet threshold
            "detailed_scores": detailed_analysis[:10]  # Top 10 for analysis
        }
        
    except Exception as e:
        return {
            "meets_threshold": False,
            "average_score": 0.0,
            "article_count": 0,
            "quality_assessment": f"Error analyzing results: {str(e)}",
            "recommendation": "try_different_strategy",
            "detailed_scores": []
        }

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
def generate_search_strategy(
    keywords_data: Dict,
    failed_strategies: List[str] = [],
    previous_results_quality: float = 0.0,
    strategy_number: int = 1
) -> Dict[str, Any]:
    """
    Generate next search strategy based on keywords and previous failures.
    
    Args:
        keywords_data: Original invention keywords and metadata
        failed_strategies: List of previously tried strategies that failed
        previous_results_quality: Quality score of previous search attempt
        strategy_number: Which strategy attempt this is (1, 2, 3, etc.)
    
    Returns:
        Search strategy with parameters and rationale
    """
    try:
        keywords = keywords_data.get('keywords', '')
        title = keywords_data.get('title', '')
        tech_description = keywords_data.get('technology_description', '')
        applications = keywords_data.get('technology_applications', '')
        
        # Parse keywords into list
        keyword_list = [k.strip() for k in keywords.split(',') if k.strip()]
        
        # Define available strategies
        strategies = [
            {
                "name": "direct_keywords",
                "search_type": "simple",
                "query_template": "core_keywords",
                "description": "Direct keyword search using core technical terms"
            },
            {
                "name": "boolean_combinations", 
                "search_type": "simple",
                "query_template": "boolean_logic",
                "description": "Boolean combinations with OR operators for synonyms"
            },
            {
                "name": "phrase_matching",
                "search_type": "simple", 
                "query_template": "phrase_search",
                "description": "Exact phrase matching for key concepts"
            },
            {
                "name": "title_focused",
                "search_type": "title_only",
                "query_template": "core_keywords",
                "description": "Search only in article titles for high relevance"
            },
            {
                "name": "methodology_focus",
                "search_type": "abstract_focus",
                "query_template": "methodology_terms", 
                "description": "Focus on methodology and process terms"
            },
            {
                "name": "application_domain",
                "search_type": "simple",
                "query_template": "application_terms",
                "description": "Search using application and use case terms"
            },
            {
                "name": "broader_domain",
                "search_type": "simple",
                "query_template": "domain_expansion",
                "description": "Broader domain search with related fields"
            }
        ]
        
        # Filter out failed strategies
        available_strategies = [s for s in strategies if s["name"] not in failed_strategies]
        
        if not available_strategies:
            return {
                "strategy_name": "exhausted",
                "search_query": "",
                "search_type": "simple",
                "rationale": "All search strategies have been attempted",
                "success_probability": 0.0
            }
        
        # Select strategy based on attempt number and previous results
        if strategy_number <= len(available_strategies):
            selected_strategy = available_strategies[strategy_number - 1]
        else:
            selected_strategy = available_strategies[-1]  # Use last available
        
        # Generate query based on template
        query = generate_query_from_template(
            selected_strategy["query_template"], 
            keyword_list, 
            title, 
            tech_description, 
            applications
        )
        
        # Estimate success probability based on strategy and previous results
        success_probability = estimate_strategy_success(
            selected_strategy, 
            previous_results_quality, 
            len(failed_strategies)
        )
        
        return {
            "strategy_name": selected_strategy["name"],
            "search_query": query,
            "search_type": selected_strategy["search_type"],
            "description": selected_strategy["description"],
            "rationale": f"Strategy {strategy_number}: {selected_strategy['description']}. Previous quality: {previous_results_quality:.3f}",
            "success_probability": success_probability,
            "phrase_search": selected_strategy["query_template"] == "phrase_search",
            "use_boolean": selected_strategy["query_template"] == "boolean_logic"
        }
        
    except Exception as e:
        return {
            "strategy_name": "error",
            "search_query": keywords,
            "search_type": "simple", 
            "rationale": f"Error generating strategy: {str(e)}",
            "success_probability": 0.1
        }

def generate_query_from_template(template: str, keywords: List[str], title: str, description: str, applications: str) -> str:
    """Generate search query based on template and available data."""
    try:
        if template == "core_keywords":
            # Use top 5-7 most important keywords
            core_terms = keywords[:7]
            return " ".join(core_terms)
        
        elif template == "boolean_logic":
            # Create Boolean combinations with OR operators
            if len(keywords) >= 4:
                tech_terms = keywords[:3]
                app_terms = keywords[3:6] if len(keywords) > 3 else keywords[1:3]
                return f"({' OR '.join(tech_terms)}) AND ({' OR '.join(app_terms)})"
            else:
                return " OR ".join(keywords)
        
        elif template == "phrase_search":
            # Extract key phrases from title and description
            phrases = []
            if title:
                # Extract potential phrases from title
                title_words = title.lower().split()
                for i in range(len(title_words) - 1):
                    phrase = f"{title_words[i]} {title_words[i+1]}"
                    if any(kw in phrase for kw in keywords):
                        phrases.append(f'"{phrase}"')
            
            if not phrases and len(keywords) >= 2:
                # Create phrases from keywords
                phrases = [f'"{keywords[0]} {keywords[1]}"']
                if len(keywords) >= 4:
                    phrases.append(f'"{keywords[2]} {keywords[3]}"')
            
            return " AND ".join(phrases) if phrases else " ".join(keywords[:3])
        
        elif template == "methodology_terms":
            # Focus on process and methodology keywords
            method_keywords = [kw for kw in keywords if any(term in kw.lower() 
                             for term in ['process', 'method', 'system', 'technique', 'approach', 'synthesis', 'production', 'formation'])]
            if method_keywords:
                return " ".join(method_keywords[:5])
            else:
                return " ".join(keywords[:5])
        
        elif template == "application_terms":
            # Focus on application and use case terms
            app_keywords = [kw for kw in keywords if any(term in kw.lower() 
                          for term in ['application', 'use', 'treatment', 'therapy', 'medical', 'clinical', 'industrial'])]
            if app_keywords:
                return " ".join(app_keywords[:5])
            else:
                # Use second half of keywords (often application-related)
                mid_point = len(keywords) // 2
                return " ".join(keywords[mid_point:mid_point+5])
        
        elif template == "domain_expansion":
            # Broader domain search with related terms
            if applications:
                app_words = applications.lower().split()[:10]
                return " ".join(app_words)
            else:
                return " ".join(keywords[:10])
        
        else:
            return " ".join(keywords[:5])
            
    except Exception as e:
        return " ".join(keywords[:5])

def estimate_strategy_success(strategy: Dict, previous_quality: float, failed_count: int) -> float:
    """Estimate probability of strategy success based on context."""
    base_probabilities = {
        "direct_keywords": 0.7,
        "boolean_combinations": 0.8,
        "phrase_matching": 0.6,
        "title_focused": 0.5,
        "methodology_focus": 0.6,
        "application_domain": 0.7,
        "broader_domain": 0.4
    }
    
    base_prob = base_probabilities.get(strategy["name"], 0.5)
    
    # Adjust based on previous failures
    failure_penalty = failed_count * 0.1
    
    # Adjust based on previous quality
    if previous_quality > 0.2:
        quality_bonus = 0.1  # Previous attempts found something
    else:
        quality_bonus = 0.0
    
    final_prob = max(0.1, min(0.9, base_prob - failure_penalty + quality_bonus))
    return round(final_prob, 2)

# =============================================================================
# LLM-POWERED SEMANTIC SEARCH TOOLS
# =============================================================================

@tool
def generate_search_synonyms(keywords: str) -> str:
    """Generate scientific synonyms for keywords to improve search results."""
    
    return f"""Generate scientific synonyms for these keywords: {keywords}

    For each keyword, provide alternative terms that researchers might use in scientific literature.

    Examples:
    - microbeads → microspheres, nanospheres, particles, beads
    - lignin → alkali lignin, kraft lignin, lignin nanoparticles  
    - surfactant-free → environment-friendly, green process
    - emulsion → dispersion, suspension, colloidal system

    Return format:
    keyword1: synonym1, synonym2, synonym3
    keyword2: synonym1, synonym2, synonym3

    Keep it simple and focus on terms that would appear in research papers."""

# These functions are now replaced by pure LLM-driven synonym generation
# No hardcoding - the LLM uses its training knowledge dynamically

# Removed hardcoded query generation - LLM now generates queries using its domain knowledge

@tool
def expand_search_query(base_query: str, expansion_type: str) -> str:
    """Expand a search query with alternative terminology."""
    
    return f"""Expand this search query: "{base_query}"

    Expansion type: {expansion_type}

    Instructions:
    - If "synonyms": Add scientific synonyms for each term
    - If "related_terms": Add related scientific terminology  
    - If "broader_domain": Expand to related research areas
    - If "process_variants": Add methodology and process alternatives
    - If "application_expansion": Add related application domains

    Return an expanded search query that researchers might use.

    Example: "lignin microbeads" → "(lignin OR alkali lignin) AND (microbeads OR microspheres OR nanospheres)"
    """


@tool
def analyze_search_gaps(original_keywords: str, search_results_summary: str) -> str:
    """Analyze why search results might be poor and suggest improvements."""
    
    prompt = f"""Analyze why our search isn't finding good results:

    Original keywords: {original_keywords}
    Current results: {search_results_summary}

    Questions to consider:
    - Are we missing important scientific synonyms?
    - Should we try different terminology that researchers use?
    - Are there related research areas we should explore?
    - What alternative terms might describe the same concepts?

    Provide:
    1. Missing terminology we should try
    2. Alternative search strategies
    3. Recommended next search terms"""
    
    return prompt

# All hardcoded analysis functions removed - LLM now uses its domain knowledge dynamically

@tool
def store_article_analysis(pdf_filename: str, article_doi: str, article_title: str, authors: str, journal: str, 
                          published_date: str, relevance_score: float, search_query: str, citation_count: int = 0, 
                          article_url: str = '', publisher: str = '', article_type: str = '', rank_position: int = 1) -> str:
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
            'search_timestamp': timestamp,
            'article_url': article_url,
            'citation_count': citation_count,
            'publisher': publisher,
            'article_type': article_type,
            'matching_keywords': search_query,
            'rank_position': rank_position
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

# Intelligent USPTO Patent Search Agent  
uspto_search_agent = Agent(
    model="us.anthropic.claude-3-7-sonnet-20250219-v1:0",
    tools=[
        read_keywords_from_dynamodb,
        generate_search_strategy, 
        search_uspto_patents,
        analyze_patent_results_quality,
        calculate_relevance_score, 
        store_patent_analysis
    ],
    system_prompt="""You are an Expert Patent Search Professional with deep USPTO database knowledge and adaptive search capabilities.

    MISSION: Find the 5 MOST RELEVANT patents using intelligent, adaptive search strategies.

    QUALITY STANDARDS:
    - Minimum relevance threshold: 25% (0.25) for patents
    - Only store patents that truly relate to the invention
    - If no patents meet threshold, try different search strategies  
    - Analyze WHY searches fail and adapt accordingly
    - Maximum 6 search attempts before giving up

    INTELLIGENT WORKFLOW:
    1. Read patent analysis data from DynamoDB
    2. Start with Strategy 1 using generate_search_strategy tool
    3. Execute search using search_uspto_patents with strategy query
    4. Calculate relevance scores and analyze quality
    5. DECISION POINT:
    - If quality meets threshold (≥0.25): Rank and store top 8
    - If quality below threshold: Generate next strategy and try again
    6. Repeat until success OR 6 attempts exhausted

    ADAPTIVE BEHAVIOR:
    - Learn from each search attempt
    - Track which keyword combinations work best
    - Adjust search terms based on result quality
    - Try different combinations: technical terms, application terms, Boolean logic
    - Progressively broaden or narrow search scope as needed

    SEARCH STRATEGY PROGRESSION:
    1. Core technical keywords (precise matching)
    2. Application domain keywords (use case focus)
    3. Boolean combinations (technical AND application)
    4. Methodology keywords (process focus)
    5. Broader technical domain (related technologies)
    6. Relaxed criteria (expanded scope)

    QUALITY ANALYSIS:
    After each search, evaluate:
    - Average relevance score of found patents
    - Number of patents above threshold
    - Whether results represent true prior art
    - Quality of patent titles and abstracts vs. invention

    DECISION MAKING:
    - If average score ≥ 0.25 AND ≥3 patents above threshold: ACCEPT
    - If average score 0.15-0.24: TRY refined strategy
    - If average score < 0.15: TRY completely different approach
    - If 6 attempts exhausted: Store best results with analysis

    USPTO SEARCH EXPERTISE:
    - Use precise technical terminology that appears in patent claims
    - Focus on mechanism, composition, and method keywords
    - Consider patent classification context
    - Look for similar inventions in same technical field
    - Evaluate patents for actual novelty impact

    FINAL STORAGE:
    Only store patents that meet quality standards:
    - Calculate final relevance scores
    - Rank by relevance (highest first)  
    - Store top 5 with rank_position 1-5
    - Include search strategy and quality assessment

    TRANSPARENCY:
    - Explain search strategy rationale
    - Report quality metrics for each attempt
    - Describe why certain strategies worked or failed
    - Provide assessment of final result quality

    You are the expert - use your judgment to find the most relevant prior art patents."""
)

# Intelligent Scholarly Article Search Agent
scholarly_article_agent = Agent(
    model="us.anthropic.claude-3-7-sonnet-20250219-v1:0",
    tools=[
        read_keywords_from_dynamodb, 
        generate_search_synonyms,
        expand_search_query,
        analyze_search_gaps,
        generate_search_strategy, 
        advanced_crossref_search, 
        analyze_search_results_quality,
        calculate_article_relevance_score, 
        store_article_analysis
    ],
    system_prompt="""You are an Expert Research Librarian with deep scientific domain knowledge and advanced semantic search capabilities.

    MISSION: Find the 8 MOST RELEVANT scholarly articles using intelligent, semantic-aware search strategies.

    QUALITY STANDARDS:
    - Minimum relevance threshold: 30% (0.3)
    - Only store articles that truly relate to the invention
    - If no articles meet threshold, use semantic expansion and try different strategies
    - Analyze WHY searches fail and adapt with domain knowledge
    - Maximum 8 search attempts before giving up (increased for semantic searches)

    SEMANTIC INTELLIGENCE WORKFLOW:
    1. Read patent analysis data from DynamoDB
    2. FIRST: Use generate_search_synonyms to expand terminology with scientific synonyms
    3. Start with Strategy 1 using expanded terminology
    4. Execute search using advanced_crossref_search with strategy parameters
    5. Analyze results quality using analyze_search_results_quality tool
    6. DECISION POINT:
    - If quality meets threshold (≥0.3): Calculate scores, rank, and store top 8
    - If quality below threshold: Use analyze_search_gaps to identify terminology issues
    - Use expand_search_query to try semantic expansions
    - Generate next strategy with improved terminology
    7. Repeat until success OR 8 attempts exhausted

    SEMANTIC SEARCH STRATEGIES:
    1. Direct keywords with scientific synonyms (baseline + expansion)
    2. Size variants (microbeads → microspheres → nanospheres → aerogel beads)
    3. Material variants (lignin → alkali lignin → kraft lignin → lignin nanoparticles)
    4. Process variants (surfactant-free → environment-friendly → green synthesis)
    5. Application expansion (personal care → drug delivery → cosmetics → biomedical)
    6. Boolean combinations with semantic terms
    7. Phrase matching with expanded terminology
    8. Broader domain search with related fields

    SEMANTIC EXPANSION EXAMPLES:
    - "microbeads" → "microspheres OR nanospheres OR aerogel beads OR particles"
    - "lignin" → "alkali lignin OR kraft lignin OR lignin nanoparticles"
    - "surfactant-free emulsion" → "environment-friendly process OR green synthesis"
    - "personal care" → "drug delivery OR cosmetic OR pharmaceutical applications"

    INTELLIGENT ADAPTATION:
    - Use generate_search_synonyms to discover scientific terminology variants
    - Use expand_search_query for targeted semantic expansion
    - Use analyze_search_gaps to understand why searches fail
    - Learn from terminology patterns in found vs. missing articles
    - Bridge gaps between invention language and research literature language

    QUALITY ANALYSIS WITH SEMANTIC AWARENESS:
    After each search, analyze:
    - Average relevance score and terminology coverage
    - Whether we're finding articles in related domains (good sign)
    - Terminology gaps that might indicate missing relevant work
    - Need for broader semantic expansion vs. narrower precision

    DECISION MAKING:
    - If ≥3 articles individually score ≥0.3: ACCEPT and store those qualifying articles
    - If 1-2 articles score ≥0.3: Use semantic expansion tools for refinement
    - If 0 articles score ≥0.3: Use analyze_search_gaps and try broader semantic expansion
    - If terminology gaps identified: Use expand_search_query with appropriate expansion type
    - If 8 attempts exhausted: Store best results found with analysis

    SEMANTIC SEARCH INTELLIGENCE:
    Remember that scientific literature uses varied terminology:
    - Invention terms ≠ Research literature terms
    - "microbeads" in patents might be "microspheres" or "nanospheres" in papers
    - "surfactant-free" might be described as "environment-friendly process"
    - Applications might be described differently (personal care vs. drug delivery)

    FINAL STORAGE:
    Store articles that meet quality standards with semantic context:
    - Calculate final relevance scores considering semantic matches
    - Rank by relevance score (highest first)
    - Store top 8 with rank_position 1-8
    - Include semantic search strategy used and terminology expansions tried

    TRANSPARENCY:
    - Explain semantic expansion choices and rationale
    - Report which terminology variants were successful
    - Describe semantic gaps identified and how they were addressed
    - Provide assessment of semantic search effectiveness

    You are a semantic search expert - use your scientific domain knowledge to bridge terminology gaps between invention language and research literature language."""
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
    5. Select top 8 most relevant scholarly articles
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
                if tool_name == "advanced_crossref_search":
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