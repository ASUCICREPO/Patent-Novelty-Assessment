# Patent Novelty PDF Processing Pipeline

A serverless pipeline that automatically processes PDF files uploaded to S3 using AWS Bedrock Data Automation (BDA) to extract text and images, then performs comprehensive patent novelty analysis using a multi-agent orchestrator system.

## Architecture

- **S3 Bucket**: Stores uploaded PDFs and processed outputs
- **Lambda Function (PDF Processor)**: Triggered by S3 events to invoke BDA processing
- **Lambda Function (Agent Trigger)**: Triggered when BDA completes to invoke Agent Core
- **Bedrock Data Automation**: Extracts text and images from PDFs
- **Patent Novelty Orchestrator**: Multi-agent system that handles keyword generation, USPTO patent search, and scholarly article search
- **DynamoDB Tables**: Store keywords, patent results, and scholarly article results
- **API Gateways**: USPTO and Crossref gateways for patent and article searches
- **CDK**: Infrastructure as Code for deployment

## Project Structure

```
backend/
├── PatentNoveltyOrchestrator/     # Multi-agent orchestrator system
│   ├── orchestrator.py            # Main orchestrator with all 4 agents
│   ├── requirements.txt           # Python dependencies
│   └── Dockerfile                 # Container configuration
├── lambda/                        # Lambda functions
│   ├── pdf_processor.py           # Triggers BDA processing
│   └── agent_trigger.py           # Triggers orchestrator
└── infrastructure/                # CDK infrastructure
    └── patent-novelty-stack.ts    # AWS resources definition

S3 Bucket Structure:
uploads/          # Upload PDF files here
temp/
  ├── docParser/  # JSON outputs from BDA
  └── temporary/  # Temporary BDA processing files
```

## Prerequisites

- AWS CLI configured with appropriate permissions
- Node.js 18+ and npm
- CDK CLI installed (`npm install -g aws-cdk`)
- Access to AWS Bedrock Data Automation service
- Access to AWS Bedrock Agent Core service

## Deployment

**One-Command Deployment**:
```bash
./deploy.sh
```

This script will:
1. Check if BDA project exists, create one if needed
2. Install all dependencies
3. Build Lambda functions
4. Deploy the complete infrastructure

**Manual Steps After Deployment**:
1. Go to AWS Console > Bedrock > Agent Core
2. Create new Agent Runtime using the Patent Orchestrator Docker image URI from CDK output
3. Use the Patent Orchestrator IAM Role ARN from CDK output
4. Configure the following environment variables in Agent Core:
   - `GATEWAY_CLIENT_ID`, `GATEWAY_CLIENT_SECRET`, `GATEWAY_TOKEN_URL`, `GATEWAY_URL` (for USPTO)
   - `CROSSREF_CLIENT_ID`, `CROSSREF_CLIENT_SECRET`, `CROSSREF_TOKEN_URL`, `CROSSREF_GATEWAY_URL` (for Crossref - fallback)
   - `SEMANTIC_SCHOLAR_CLIENT_ID`, `SEMANTIC_SCHOLAR_CLIENT_SECRET`, `SEMANTIC_SCHOLAR_TOKEN_URL`, `SEMANTIC_SCHOLAR_GATEWAY_URL` (for Semantic Scholar - primary)
5. Update the `AGENT_RUNTIME_ARN` in the CDK stack with the created runtime ARN
6. Redeploy: `npx cdk deploy`

## Usage

1. Upload a PDF file to the `uploads/` folder in your S3 bucket
2. The PDF processor Lambda function will automatically trigger BDA processing
3. BDA processes the PDF and outputs JSON to `temp/docParser/`
4. The agent trigger Lambda function automatically detects the BDA completion
5. Patent Novelty Orchestrator is invoked to:
   - Generate patent search keywords from the document
   - Search USPTO patents for prior art
   - Search scholarly articles for academic context
6. Results are stored in DynamoDB tables and logged

## Automated Pipeline Flow

```
PDF Upload → BDA Processing → result.json → Agent Trigger → Orchestrator → [Keywords + USPTO Search + Scholarly Search]
```

## Multi-Agent Orchestrator

The system uses a single orchestrator that manages three specialized agents:

1. **Keyword Generator Agent**: Extracts patent search keywords from BDA results
2. **USPTO Search Agent**: Searches patents using extracted keywords via USPTO Gateway
3. **Scholarly Article Agent**: Searches academic literature via Semantic Scholar Gateway (primary) and Crossref Gateway (fallback)

Each agent can be invoked independently by specifying the appropriate action:
- `action: "generate_keywords"` - Keyword generation
- `action: "search_patents"` - USPTO patent search  
- `action: "search_articles"` - Scholarly article search

## Monitoring

- Check CloudWatch logs for both Lambda functions to monitor processing status
- Use Agent Core observability features to view agent execution details
- Monitor S3 bucket for BDA processing outputs

## Clean Up

```bash
npx cdk destroy
```

## Environment Variables

### PDF Processor Lambda
- `BUCKET_NAME`: S3 bucket name
- `BDA_PROJECT_ARN`: Bedrock Data Automation project ARN

### Agent Trigger Lambda  
- `AGENT_RUNTIME_ARN`: Agent Core runtime ARN (format: `arn:aws:bedrock-agentcore:REGION:ACCOUNT:runtime/RUNTIME-ID`)

### Patent Novelty Orchestrator (Agent Core Runtime)
- `BUCKET_NAME`: S3 bucket name
- `KEYWORDS_TABLE_NAME`: DynamoDB table for patent keywords
- `RESULTS_TABLE_NAME`: DynamoDB table for USPTO patent results
- `ARTICLES_TABLE_NAME`: DynamoDB table for scholarly article results
- `GATEWAY_CLIENT_ID`, `GATEWAY_CLIENT_SECRET`, `GATEWAY_TOKEN_URL`, `GATEWAY_URL`: USPTO Gateway configuration
- `CROSSREF_CLIENT_ID`, `CROSSREF_CLIENT_SECRET`, `CROSSREF_TOKEN_URL`, `CROSSREF_GATEWAY_URL`: Crossref Gateway configuration (fallback)
- `SEMANTIC_SCHOLAR_CLIENT_ID`, `SEMANTIC_SCHOLAR_CLIENT_SECRET`, `SEMANTIC_SCHOLAR_TOKEN_URL`, `SEMANTIC_SCHOLAR_GATEWAY_URL`: Semantic Scholar Gateway configuration (primary)

## Scholarly Article Search Services

### Semantic Scholar (Primary)
- **API**: Semantic Scholar Academic Graph API
- **Authentication**: API Key via Agent Core Token Vault
- **Token Vault ARN**: `arn:aws:bedrock-agentcore:us-west-2:216989103356:token-vault/default/apikeycredentialprovider/semantic-scholar`
- **Advantages**: 
  - Comprehensive academic paper database
  - Advanced relevance ranking algorithm
  - Field-of-study classifications
  - Citation metrics and open access indicators
  - Better coverage of recent research

### Crossref (Fallback)
- **API**: Crossref REST API
- **Authentication**: OAuth 2.0 + polite pool access
- **Usage**: Fallback service if Semantic Scholar fails
- **Advantages**: 
  - Broad coverage of published literature
  - DOI-based identification system
  - Publisher metadata

## DynamoDB Tables

### Keywords Table
Stores patent analysis results from keyword generation:
- `pdf_filename` (partition key): Name of the processed PDF
- `timestamp` (sort key): Processing timestamp
- `title`: Extracted invention title
- `technology_description`: Technical description of the invention
- `technology_applications`: Applications and use cases
- `keywords`: Comma-separated patent search keywords

### Patent Results Table  
Stores USPTO patent search results:
- `pdf_filename` (partition key): Name of the processed PDF
- `patent_number` (sort key): USPTO patent number
- `patent_title`, `patent_inventors`, `patent_assignee`: Patent metadata
- `relevance_score`: Calculated relevance to original invention
- `search_strategy_used`: Keywords used for this search

### Scholarly Articles Table
Stores scholarly article search results from Semantic Scholar (primary) and Crossref (fallback):
- `pdf_filename` (partition key): Name of the processed PDF  
- `article_doi` (sort key): Article DOI/Paper ID
- `article_title`, `authors`, `journal`: Article metadata
- `relevance_score`: Calculated relevance to original invention
- `citation_count`: Number of citations
- `fields_of_study`: Academic field classifications (Semantic Scholar)
- `open_access_pdf_url`: Direct link to open access PDF (Semantic Scholar)
- `publisher`: Source service (Semantic Scholar or Crossref)