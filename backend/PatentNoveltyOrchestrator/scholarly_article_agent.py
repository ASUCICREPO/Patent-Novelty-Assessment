#!/usr/bin/env python3
"""
Scholarly Article Search Agent
Searches Semantic Scholar for relevant academic papers using LLM-driven adaptive search.
"""
import json
import os
import boto3
import requests
import time
from datetime import datetime
from decimal import Decimal
from typing import Dict, Any, List
from strands import Agent, tool
from strands.tools.mcp.mcp_client import MCPClient
from mcp.client.streamable_http import streamablehttp_client
from patent_search_agent import read_keywords_from_dynamodb, create_streamable_http_transport, get_full_tools_list

# Environment Variables
AWS_REGION = os.getenv('AWS_REGION', 'us-west-2')
ARTICLES_TABLE = os.getenv('ARTICLES_TABLE_NAME')

# Gateway Configuration for Semantic Scholar Search
SEMANTIC_SCHOLAR_CLIENT_ID = os.environ.get('SEMANTIC_SCHOLAR_CLIENT_ID')
SEMANTIC_SCHOLAR_CLIENT_SECRET = os.environ.get('SEMANTIC_SCHOLAR_CLIENT_SECRET')
SEMANTIC_SCHOLAR_TOKEN_URL = os.environ.get('SEMANTIC_SCHOLAR_TOKEN_URL')
SEMANTIC_SCHOLAR_GATEWAY_URL = os.environ.get('SEMANTIC_SCHOLAR_GATEWAY_URL')

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
# AGENT DEFINITION
# =============================================================================

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
