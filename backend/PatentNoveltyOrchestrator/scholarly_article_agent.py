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

def run_semantic_scholar_search_clean(search_query: str, limit: int = 10):
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
                modelId="global.anthropic.claude-sonnet-4-5-20250929-v1:0",
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
        
        # PHASE 2: Execute searches (no refinement)
        print("Phase 2: Executing searches...")
        all_relevant_papers = []
        
        for query_info in search_queries:
            print(f"Executing search: '{query_info['query']}'")
            
            # Execute search with rate limiting
            result = run_semantic_scholar_search_clean(
                search_query=query_info['query'],
                limit=10  # OPTIMIZATION: Reduced from 20 to 10
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
                        
                        # OPTIMIZATION: Removed quality assessment and refinement logic
                        # Proceed directly with articles
                        current_articles = articles
                        
                        # Collect papers for batch processing (no individual evaluation yet)
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
                            
                            # OPTIMIZATION: Just collect papers, no evaluation yet
                            all_relevant_papers.append(processed_article)
                            print(f"COLLECTED: {processed_article['title'][:60]}...")
                                
                    except json.JSONDecodeError as je:
                        print(f"JSON decode error for query '{query_info['query']}': {je}")
                else:
                    print(f"No content in result for query '{query_info['query']}'")
            else:
                print(f"No result for query '{query_info['query']}'")
        
        print(f"\n{'='*80}")
        print(f"OPTIMIZATION PHASE: Deduplication and Pre-filtering")
        print(f"{'='*80}")
        print(f"Total papers collected: {len(all_relevant_papers)}")
        
        # OPTIMIZATION 1: Remove duplicates BEFORE evaluation
        unique_papers = {}
        for paper in all_relevant_papers:
            paper_id = paper['paperId']
            if paper_id not in unique_papers:
                unique_papers[paper_id] = paper
        
        papers_list = list(unique_papers.values())
        print(f"After deduplication: {len(papers_list)} unique papers")
        
        # OPTIMIZATION 2: Pre-filter by citations (top 30) BEFORE LLM evaluation
        papers_sorted_by_citations = sorted(papers_list, key=lambda x: x.get('citation_count', 0), reverse=True)
        top_cited_papers = papers_sorted_by_citations[:30]
        print(f"After citation pre-filtering: {len(top_cited_papers)} papers (top 30 by citations)")
        
        # OPTIMIZATION 3: Batch LLM evaluation (1 call instead of 30)
        print(f"\nBatch evaluating {len(top_cited_papers)} papers with LLM...")
        evaluations = evaluate_papers_batch_llm(top_cited_papers, keywords_data)
        
        # Attach evaluations to papers
        for i, paper in enumerate(top_cited_papers):
            if i < len(evaluations):
                paper['llm_relevance_score'] = evaluations[i].get('relevance_score', 0)
                paper['technical_overlaps'] = evaluations[i].get('technical_overlaps', [])
                paper['novelty_impact_assessment'] = evaluations[i].get('novelty_impact_assessment', '')
            else:
                # Fallback if evaluation missing
                paper['llm_relevance_score'] = 0
                paper['technical_overlaps'] = []
                paper['novelty_impact_assessment'] = 'Evaluation not available'
        
        # Calculate combined score for each paper: LLM score (60%) + Citation impact (40%)
        for paper in top_cited_papers:
            llm_score = paper.get('llm_relevance_score', 0) / 10.0  # Normalize to 0-1
            citation_score = min(paper.get('citation_count', 0) / 100.0, 1.0)  # Normalize, cap at 100 citations = 1.0
            paper['combined_score'] = (llm_score * 0.6) + (citation_score * 0.4)
        
        # Sort by combined score and take top 8
        final_papers = sorted(top_cited_papers, key=lambda x: x['combined_score'], reverse=True)[:8]
        
        print(f"\n{'='*80}")
        print(f"FINAL SELECTION: Top {len(final_papers)} papers for patent novelty assessment")
        print(f"{'='*80}")
        for i, paper in enumerate(final_papers, 1):
            print(f"\n{i}. {paper['title'][:70]}...")
            print(f"   LLM Score: {paper.get('llm_relevance_score', 0)}/10 | Citations: {paper['citation_count']} | Combined: {paper['combined_score']:.3f}")
            print(f"   Impact: {paper['novelty_impact_assessment'][:100]}...")
        print(f"\n{'='*80}\n")
        
        return final_papers
        
    except Exception as e:
        print(f"Error in strategic Semantic Scholar search: {e}")
        import traceback
        traceback.print_exc()
        return []

def evaluate_papers_batch_llm(papers_list: List[Dict], invention_context: Dict) -> List[Dict]:
    """
    OPTIMIZATION: Evaluate multiple papers in ONE LLM call instead of individual calls.
    This reduces LLM calls from 30+ to 1.
    """
    try:
        if not papers_list:
            return []
        
        # Extract invention context
        invention_title = invention_context.get('title', 'Unknown Invention')
        tech_description = invention_context.get('technology_description', '')
        tech_applications = invention_context.get('technology_applications', '')
        keywords = invention_context.get('keywords', '')
        
        # Build prompt with all papers
        papers_text = ""
        for i, paper in enumerate(papers_list, 1):
            paper_title = paper.get('title', 'Unknown Title')
            paper_abstract = paper.get('abstract', 'No abstract available')
            paper_authors = paper.get('authors', 'Unknown Authors')
            paper_venue = paper.get('venue', 'Unknown Venue')
            paper_year = paper.get('published_date', 'Unknown')
            paper_id = paper.get('paperId', 'unknown')
            
            # Skip papers without sufficient abstract
            if not paper_abstract or len(paper_abstract.strip()) < 50:
                paper_abstract = "Abstract too short or missing - cannot evaluate"
            
            papers_text += f"""
            Paper {i}:
            ID: {paper_id}
            Title: {paper_title}
            Authors: {paper_authors}
            Venue: {paper_venue}
            Year: {paper_year}
            Abstract: {paper_abstract}
            """
        
        batch_prompt = f"""You are a patent novelty assessment expert. Evaluate ALL {len(papers_list)} research papers for relevance to the invention.

        INVENTION TO ASSESS:
        Title: {invention_title}
        Technical Description: {tech_description}
        Applications: {tech_applications}
        Key Technologies: {keywords}

        PAPERS TO EVALUATE:
        {papers_text}

        TASK: Evaluate each paper's relevance for patent novelty assessment (0-10 scale).

        For each paper, analyze:
        1. TECHNICAL OVERLAP: Similar technologies, methods, or mechanisms?
        2. PROBLEM DOMAIN: Same or related problems?
        3. APPLICATION SIMILARITY: Similar use cases or applications?
        4. PRIOR ART POTENTIAL: Could affect novelty?

        RESPOND WITH A JSON ARRAY (one object per paper, in order):
        [
        {{
            "paper_id": "paper_id_here",
            "relevance_score": 8,
            "technical_overlaps": ["overlap1", "overlap2"],
            "novelty_impact_assessment": "Brief assessment (2-3 sentences) explaining relevance, overlaps, and potential impact on novelty claims"
        }},
        ...
        ]

        SCORING GUIDELINES:
        - 9-10: Directly describes same/very similar invention
        - 7-8: Highly relevant, significant technical overlap
        - 5-6: Moderately relevant, some overlap
        - 3-4: Tangentially related, minimal overlap
        - 0-2: Not relevant or very weak connection

        IMPORTANT: Provide assessment for ALL {len(papers_list)} papers in order. Be concise but specific."""

        # Make single LLM call for all papers
        bedrock_client = boto3.client('bedrock-runtime', region_name=AWS_REGION)
        request_body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 4000,  # Increased for batch response
            "messages": [
                {
                    "role": "user",
                    "content": batch_prompt
                }
            ]
        }
        
        print(f"Making batch LLM call for {len(papers_list)} papers...")
        response = bedrock_client.invoke_model(
            modelId="global.anthropic.claude-sonnet-4-5-20250929-v1:0",
            body=json.dumps(request_body)
        )
        
        # Parse response
        response_body = json.loads(response['body'].read())
        llm_response = response_body['content'][0]['text']
        
        # Extract JSON array
        json_start = llm_response.find('[')
        json_end = llm_response.rfind(']') + 1
        
        if json_start != -1 and json_end != -1:
            json_str = llm_response[json_start:json_end]
            evaluations = json.loads(json_str)
            print(f"✓ Batch evaluation successful: {len(evaluations)} papers evaluated")
            return evaluations
        else:
            print("⚠ Could not parse JSON from batch LLM response")
            # Return default evaluations
            return [
                {
                    'paper_id': paper.get('paperId', 'unknown'),
                    'relevance_score': 0,
                    'technical_overlaps': [],
                    'novelty_impact_assessment': 'Batch evaluation parsing failed'
                }
                for paper in papers_list
            ]
            
    except Exception as e:
        print(f"Error in batch LLM evaluation: {e}")
        import traceback
        traceback.print_exc()
        # Return default evaluations
        return [
            {
                'paper_id': paper.get('paperId', 'unknown'),
                'relevance_score': 0,
                'technical_overlaps': [],
                'novelty_impact_assessment': f'Batch evaluation failed: {str(e)}'
            }
            for paper in papers_list
        ]

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

@tool
def store_semantic_scholar_analysis(pdf_filename: str, article_data: Dict[str, Any]) -> str:
    """Store LLM-analyzed Semantic Scholar article in DynamoDB with enhanced metadata."""
    try:
        dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
        table = dynamodb.Table(ARTICLES_TABLE)
        timestamp = datetime.utcnow().isoformat()
        paper_id = article_data.get('paperId', 'unknown')
        article_title = article_data.get('title', 'Unknown Title')

        # Use the combined score calculated during search (LLM 60% + Citations 40%)
        # This is the final relevance score used for ranking
        relevance_score = article_data.get('combined_score', 0.0)
        
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
            'fields_of_study': ', '.join(article_data.get('fields_of_study', [])) if article_data.get('fields_of_study') else '',
            'open_access_pdf_url': article_data.get('open_access_pdf', ''),
            'search_query_used': article_data.get('search_query_used', ''),
            'abstract': article_data.get('abstract', ''),
            
            # Final relevance score (LLM 60% + Citations 40%, normalized 0-1)
            'relevance_score': Decimal(str(relevance_score)),
            'key_technical_overlaps': ', '.join(article_data.get('technical_overlaps', [])) if article_data.get('technical_overlaps') else '',
            'novelty_impact_assessment': article_data.get('novelty_impact_assessment', ''),
            'matching_keywords': article_data.get('search_query_used', ''),
            
            # Report Control
            'add_to_report': 'No',  # Default to No - user must manually change to Yes
        }
        table.put_item(Item=item)
        return f"Successfully stored LLM-analyzed article {paper_id}: {article_title} (Relevance Score: {relevance_score:.3f})"
        
    except Exception as e:
        return f"Error storing Semantic Scholar article {article_data.get('paperId', 'unknown')}: {str(e)}"


# =============================================================================
# AGENT DEFINITION
# =============================================================================

scholarly_article_agent = Agent(
    model="global.anthropic.claude-sonnet-4-5-20250929-v1:0",
    tools=[read_keywords_from_dynamodb, search_semantic_scholar_articles_strategic, 
           store_semantic_scholar_analysis],
    system_prompt="""You are an Intelligent Scholarly Article Search Expert using OPTIMIZED LLM-driven search for Patent Novelty Assessment.

    EXECUTE THIS WORKFLOW EXACTLY:

    1. READ INVENTION CONTEXT
    - Use read_keywords_from_dynamodb to get complete invention data
    - Extract title, technology description, applications, and keywords

    2. EXECUTE OPTIMIZED INTELLIGENT SEARCH
    - Use search_semantic_scholar_articles_strategic with the full invention context
    - This OPTIMIZED tool will automatically:
      * Generate optimal search queries using LLM analysis
      * Execute 5 searches (10 papers each = 50 total papers)
      * Deduplicate papers (~30-40 unique papers)
      * Pre-filter to top 30 by citation count
      * Batch evaluate all 30 papers in ONE LLM call (not 30 separate calls)
      * Rank by combined score (LLM 60% + Citations 40%)
      * Return top 8 most relevant papers

    3. STORE RESULTS - ONE AT A TIME
    - For each paper returned by the strategic search, call store_semantic_scholar_analysis
    - Store papers SEQUENTIALLY: Call tool → Wait for result → Call next tool
    - DO NOT call multiple store_semantic_scholar_analysis in the same turn
    - Pass the complete paper data object which includes LLM analysis results
    - Continue until all 8 papers are stored

    CRITICAL PRINCIPLES:
    - Focus on semantic relevance, not just keyword matching
    - Store all papers returned by the strategic search (top 8 by combined score)
    - Target exactly 8 papers ranked by relevance for comprehensive novelty assessment
    - SEQUENTIAL EXECUTION: Store papers one at a time, waiting for each result before the next call

    QUALITY ASSURANCE:
    - Papers are ranked by combined score (LLM 60% + Citations 40%)
    - Top 8 papers are returned regardless of absolute scores
    - Detailed novelty impact assessments and technical overlaps are captured
    - Examiners can review all 8 papers with scores to make final relevance decisions

    Your goal: Execute the OPTIMIZED search workflow to identify and rank the top 8 academic papers by relevance, providing comprehensive LLM-powered novelty impact assessments for each paper to support patent examination."""
)
