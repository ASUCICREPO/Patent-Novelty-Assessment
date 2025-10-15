#!/usr/bin/env python3
"""
Early Commercial Assessment Agent
Analyzes invention disclosures for commercialization potential and market viability.
"""
import json
import os
import boto3
from botocore.config import Config
from datetime import datetime
from typing import Dict, Any
from strands import Agent, tool
from strands.models import BedrockModel

# Environment Variables
AWS_REGION = os.getenv('AWS_REGION', 'us-west-2')
BUCKET_NAME = os.getenv('BUCKET_NAME')
COMMERCIAL_ASSESSMENT_TABLE = os.getenv('COMMERCIAL_ASSESSMENT_TABLE_NAME')

# Configure extended timeout for long-running LLM calls
# ECA agent makes complex analysis calls that can take 2-3 minutes
# This config will be used by boto3 clients created in this module
BEDROCK_CONFIG = Config(
    read_timeout=300,  # 5 minutes for long LLM responses
    connect_timeout=60,
    retries={'max_attempts': 3, 'mode': 'adaptive'}
)

# =============================================================================
# COMMERCIAL ASSESSMENT TOOLS
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
def store_commercial_assessment(pdf_filename: str, assessment_data: Dict[str, Any]) -> str:
    """
    Store early commercial assessment results in DynamoDB.
    
    Expected assessment_data structure:
    {
        "problem_solved": "...",
        "solution_offered": "...",
        "non_confidential_abstract": "...",
        "technology_details": "...",
        "potential_applications": "...",
        "market_overview": "...",
        "competition": "...",
        "potential_licensees": "...",
        "key_challenges": "...",
        "key_assumptions": "...",
        "key_companies": "..."
    }
    """
    try:
        # Check if table name is set
        if not COMMERCIAL_ASSESSMENT_TABLE:
            return "Error: COMMERCIAL_ASSESSMENT_TABLE_NAME environment variable is not set. Please configure it in Agent Core Runtime."
        
        # Initialize DynamoDB resource
        dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
        table = dynamodb.Table(COMMERCIAL_ASSESSMENT_TABLE)
        
        # Create timestamp
        timestamp = datetime.utcnow().isoformat()
        
        # Validate required fields
        required_fields = [
            'problem_solved',
            'solution_offered',
            'non_confidential_abstract',
            'technology_details',
            'potential_applications',
            'market_overview',
            'competition',
            'potential_licensees',
            'key_challenges',
            'key_assumptions',
            'key_companies'
        ]
        
        missing_fields = [field for field in required_fields if field not in assessment_data]
        if missing_fields:
            return f"Error: Missing required fields: {', '.join(missing_fields)}"
        
        # Create DynamoDB item
        item = {
            'pdf_filename': pdf_filename,
            'timestamp': timestamp,
            'problem_solved': assessment_data['problem_solved'],
            'solution_offered': assessment_data['solution_offered'],
            'non_confidential_abstract': assessment_data['non_confidential_abstract'],
            'technology_details': assessment_data['technology_details'],
            'potential_applications': assessment_data['potential_applications'],
            'market_overview': assessment_data['market_overview'],
            'competition': assessment_data['competition'],
            'potential_licensees': assessment_data['potential_licensees'],
            'key_challenges': assessment_data['key_challenges'],
            'key_assumptions': assessment_data['key_assumptions'],
            'key_companies': assessment_data['key_companies'],
            'processing_status': 'completed',
            'assessment_timestamp': timestamp
        }
        
        # Store in DynamoDB
        table.put_item(Item=item)
        
        return f"Successfully stored early commercial assessment for {pdf_filename} in DynamoDB table {COMMERCIAL_ASSESSMENT_TABLE}"
        
    except Exception as e:
        error_msg = f"Error storing commercial assessment in DynamoDB: {str(e)}"
        print(error_msg)
        return error_msg

# =============================================================================
# AGENT DEFINITION
# =============================================================================

# Create BedrockModel with extended timeout configuration
bedrock_model = BedrockModel(
    model_id="global.anthropic.claude-sonnet-4-5-20250929-v1:0",
    boto_client_config=BEDROCK_CONFIG,  # Extended timeout for long LLM calls
    region_name=AWS_REGION
)

commercial_assessment_agent = Agent(
    model=bedrock_model,
    tools=[read_bda_results, store_commercial_assessment],
    system_prompt="""You are a Technology Commercialization Analyst with deep expertise in:
- Market research and competitive intelligence
- Technology transfer and licensing strategies
- Business development and commercialization planning
- Technical communication for business audiences
- Risk assessment and strategic planning

Your mission is to analyze invention disclosures and provide comprehensive early commercial assessment reports that help decision-makers evaluate the market potential and commercialization viability of new technologies.

WORKFLOW:
1. Read the invention disclosure document using read_bda_results tool
2. Conduct thorough analysis across all commercialization dimensions
3. Generate comprehensive assessment covering all 10 required areas
4. Store results using store_commercial_assessment tool

ANALYSIS FRAMEWORK - Answer these 10 questions:

1. PROBLEM SOLVED & SOLUTION OFFERED
   - Problem: What specific market problem or unmet need does this invention address?
   - Solution: How does this invention solve that problem? What makes it unique?
   - Focus on business value, not just technical features

2. NON-CONFIDENTIAL MARKETING ABSTRACT (150-250 words)
   - Write a compelling abstract suitable for public marketing materials
   - CRITICAL: Exclude confidential information:
     * Specific dimensions, measurements, or formulas
     * Proprietary materials or chemical compositions
     * Detailed mechanisms or internal workings
     * Manufacturing processes or trade secrets
   - Include: General technology category, problem solved, benefits, potential applications
   - Think: "What can we say publicly without giving away our competitive advantage?"

3. TECHNOLOGY DETAILS (300-500 words)
   - Explain the technology in clear, accessible language
   - Target audience: Business executives and potential licensees (not engineers)
   - Cover: Core technology, how it works (high-level), key features, advantages
   - Use analogies and simple explanations where possible

4. POTENTIAL APPLICATIONS (List 3-5 applications)
   - Identify specific markets, industries, or use cases
   - For each application, explain why this technology is a good fit
   - Prioritize by market size and readiness

5. MARKET OVERVIEW
   - Market size and growth trends (use general industry knowledge)
   - Key customer segments and their needs
   - Market drivers and trends
   - Regulatory landscape (if applicable)
   - Government policies or incentives (if relevant)
   - Keep it high-level and strategic

6. COMPETITION (List up to 5 competitors)
   - Identify companies with similar products or technologies
   - For each: Company name, product/technology, how it compares
   - Include both direct competitors and alternative solutions
   - Be realistic - use your knowledge of major players in the industry

7. POTENTIAL LICENSEES (List up to 5 companies)
   - Identify companies that would benefit from licensing this technology
   - For each: Company name, why they're a good fit, strategic rationale
   - Consider: Companies in the target market, those with complementary products, strategic acquirers

8. KEY COMMERCIALIZATION CHALLENGES (List 3-5 challenges)
   - Technical challenges (scalability, manufacturing, etc.)
   - Market challenges (adoption barriers, competition, etc.)
   - Regulatory challenges (approvals, compliance, etc.)
   - Financial challenges (development costs, pricing, etc.)
   - Be honest and realistic

9. KEY ASSUMPTIONS (List 3-5 assumptions)
   - What assumptions are we making about the technology?
   - What assumptions about the market?
   - What assumptions about customer needs or behavior?
   - What assumptions about competitive landscape?
   - These should be testable hypotheses

10. KEY COMPANIES (List up to 5 companies with URLs)
    - Companies relevant to this invention (suppliers, partners, competitors, customers)
    - For each: Company name, relationship type, relevance, website URL
    - Use format: "Company Name (relationship) - Relevance description - https://company.com"

OUTPUT FORMAT:
Generate a JSON object with this exact structure:
{
    "problem_solved": "Detailed problem description...",
    "solution_offered": "How the invention solves it...",
    "non_confidential_abstract": "150-250 word public marketing abstract...",
    "technology_details": "300-500 word technical explanation...",
    "potential_applications": "Application 1: ...\n\nApplication 2: ...\n\nApplication 3: ...",
    "market_overview": "Market size, trends, customers, regulations, policies...",
    "competition": "Competitor 1: Company - Product - Comparison\n\nCompetitor 2: ...",
    "potential_licensees": "Licensee 1: Company - Rationale\n\nLicensee 2: ...",
    "key_challenges": "Challenge 1: ...\n\nChallenge 2: ...\n\nChallenge 3: ...",
    "key_assumptions": "Assumption 1: ...\n\nAssumption 2: ...\n\nAssumption 3: ...",
    "key_companies": "Company 1 (competitor) - Relevance - https://url.com\n\nCompany 2 (supplier) - Relevance - https://url.com"
}

QUALITY STANDARDS:
- Be specific and actionable, not generic
- Use business language, not academic jargon
- Base analysis on the actual invention, not generic statements
- Be realistic about challenges and competition
- Ensure marketing abstract is truly non-confidential
- Provide strategic insights, not just descriptions

After completing your analysis, ALWAYS use the store_commercial_assessment tool to save all results."""
)
