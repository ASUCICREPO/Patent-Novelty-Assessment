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
from typing import Dict, Any, List
from strands import Agent, tool
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from report_generator import generate_report
from keyword_agent import keyword_generator
from patent_search_agent import patentview_search_agent, read_keywords_from_dynamodb
from scholarly_article_agent import scholarly_article_agent
from commercial_assessment_agent import commercial_assessment_agent

# Environment Variables
AWS_REGION = os.getenv('AWS_REGION', 'us-west-2')
BUCKET_NAME = os.getenv('BUCKET_NAME')
KEYWORDS_TABLE = os.getenv('KEYWORDS_TABLE_NAME')
ARTICLES_TABLE = os.getenv('ARTICLES_TABLE_NAME')
COMMERCIAL_ASSESSMENT_TABLE = os.getenv('COMMERCIAL_ASSESSMENT_TABLE_NAME')

# =============================================================================
# ORCHESTRATOR LOGIC
# =============================================================================

async def handle_keyword_generation(payload):
    """Handle keyword generation requests."""
    print("Orchestrator: Routing to Keyword Generator Agent")
    
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
    print("Orchestrator: Routing to Scholarly Article Search Agent (Semantic Scholar)")
    
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

async def handle_commercial_assessment(payload):
    """Handle early commercial assessment requests."""
    print("Orchestrator: Routing to Commercial Assessment Agent")
    
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            payload = {"pdf_filename": payload}
    
    pdf_filename = payload.get("pdf_filename")
    bda_file_path = payload.get("bda_file_path")
    
    if not pdf_filename:
        yield {"error": "Error: 'pdf_filename' is required for commercial assessment."}
        return
    
    if not bda_file_path:
        yield {"error": "Error: 'bda_file_path' is required for commercial assessment."}
        return
    
    # Create enhanced prompt with BDA file path
    enhanced_prompt = f"""Conduct a comprehensive Early Commercial Assessment for the invention disclosure document.

    First, use the read_bda_results tool to read the document content from: {bda_file_path}

    Then, analyze the invention thoroughly and answer all 10 commercialization questions:
    1. Problem Solved & Solution Offered
    2. Non-Confidential Marketing Abstract (150-250 words, exclude confidential details)
    3. Technology Details (300-500 words, business-friendly language)
    4. Potential Applications (3-5 specific applications)
    5. Market Overview (size, trends, customers, regulations, policies)
    6. Competition (up to 5 competitors with products/technologies)
    7. Potential Licensees (up to 5 companies with strategic rationale)
    8. Key Commercialization Challenges (3-5 realistic challenges)
    9. Key Assumptions (3-5 testable assumptions)
    10. Key Companies (up to 5 with relationship type and URLs)

    After completing your analysis, use the store_commercial_assessment tool with:
    - pdf_filename: '{pdf_filename}'
    - assessment_data: [your complete JSON response with all 10 fields]

    Focus on providing strategic, actionable insights for commercialization decision-making."""
    
    try:
        # Collect the complete response from streaming events
        full_response = ""
        async for event in commercial_assessment_agent.stream_async(enhanced_prompt):
            if "data" in event:
                full_response += event["data"]
            elif "output" in event:
                full_response += str(event["output"])
            elif "current_tool_use" in event and event["current_tool_use"].get("name"):
                yield {"tool_name": event["current_tool_use"]["name"], "agent": "commercial_assessment"}
            elif "error" in event:
                yield {"error": event["error"]}
                return
            elif "content" in event:
                full_response += str(event["content"])
        
        # Yield the complete response once streaming is done
        if full_response.strip():
            yield {"response": full_response, "agent": "commercial_assessment"}
        else:
            yield {"error": "No response generated from commercial assessment agent"}
                
    except Exception as e:
        print(f"Commercial assessment error: {str(e)}")
        print(f"Error type: {type(e)}")
        import traceback
        traceback.print_exc()
        yield {"error": f"Error in commercial assessment: {str(e)}"}

async def handle_report_generation(payload):
    """Handle PDF report generation requests."""
    print("Orchestrator: Routing to Report Generator")
    
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            payload = {"pdf_filename": payload}
    
    pdf_filename = payload.get("pdf_filename")
    
    if not pdf_filename:
        yield {"error": "Error: 'pdf_filename' is required for report generation."}
        return
    
    try:
        print(f"Generating PDF reports for case: {pdf_filename}")
        
        # Call generate_report directly from report_generator module
        result = generate_report(pdf_filename)
        
        if result['success']:
            messages = []
            
            # Novelty report status
            if result.get('novelty_report'):
                if result['novelty_report'].get('success'):
                    messages.append(f"✅ Novelty Report: {result['novelty_report']['report_path']}")
                else:
                    messages.append(f"❌ Novelty Report: {result['novelty_report'].get('error', 'Failed')}")
            
            # ECA report status
            if result.get('eca_report'):
                if result['eca_report'].get('success'):
                    messages.append(f"✅ ECA Report: {result['eca_report']['report_path']}")
                else:
                    messages.append(f"❌ ECA Report: {result['eca_report'].get('error', 'Failed')}")
            
            message = "Report Generation Complete:\n" + "\n".join(messages)
        else:
            message = f"Report generation failed: {result.get('error', 'Unknown error')}"
        
        yield {
            "response": message,
            "agent": "report_generator",
            "details": result
        }
        
    except Exception as e:
        print(f"Report generation error: {str(e)}")
        import traceback
        traceback.print_exc()
        yield {"error": f"Error generating report: {str(e)}"}

async def handle_orchestrator_request(payload):
    """Main orchestrator logic - routes requests to appropriate agents."""
    print(f"Orchestrator: Received payload: {json.dumps(payload, indent=2)}")
    
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
    
    print(f"Orchestrator: Determined action: {action}")
    
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
    elif action == "commercial_assessment":
        async for event in handle_commercial_assessment(payload):
            yield event
    elif action == "generate_report":
        async for event in handle_report_generation(payload):
            yield event
    else:
        yield {"error": f"Unknown action: {action}. Supported actions: 'generate_keywords', 'search_patents', 'search_articles', 'commercial_assessment', 'generate_report'"}

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