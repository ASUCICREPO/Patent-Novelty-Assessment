# Patent Novelty Assessment System

An AI-powered patent novelty assessment and early commercial evaluation platform built on AWS Bedrock Agent Core. This system automatically analyzes invention disclosure documents to assess patent novelty through prior art searches and evaluates commercialization potential.

## 🎯 Overview

This system processes invention disclosure PDFs and provides:

- **Patent Novelty Assessment** - Searches USPTO PatentView database for prior art
- **Academic Literature Search** - Searches Semantic Scholar for relevant research papers
- **Early Commercial Assessment (ECA)** - Analyzes market potential and commercialization viability
- **Professional PDF Reports** - Generates comprehensive assessment reports

## 🏗️ Architecture

### High-Level Flow

```
User uploads PDF
    ↓
AWS Bedrock Data Automation (BDA) extracts text
    ↓
Lambda triggers Orchestrator Agent
    ↓
┌─────────────────────────────────────────────────────┐
│              Multi-Agent Orchestration              │
│                                                     │
│  1. Keyword Generator Agent                        │
│     └─→ Extracts keywords, title, descriptions     │
│                                                     │
│  2. Commercial Assessment Agent (Auto-triggered)   │
│     └─→ Analyzes commercialization potential       │
│                                                     │
│  3. Patent Search Agent (User-triggered)           │
│     └─→ Searches PatentView via Gateway            │
│                                                     │
│  4. Scholarly Article Agent (User-triggered)       │
│     └─→ Searches Semantic Scholar via Gateway      │
│                                                     │
│  5. Report Generator (User-triggered)              │
│     └─→ Generates PDF reports                      │
└─────────────────────────────────────────────────────┘
    ↓
Results stored in DynamoDB
    ↓
PDF reports uploaded to S3
```

### Component Architecture

```
┌──────────────┐
│    Users     │
└──────┬───────┘
       │
       ↓
┌──────────────────────────────────────────────────────┐
│              Frontend (Amplify UI)                   │
│  - Upload PDFs                                       │
│  - View results                                      │
│  - Trigger agents                                    │
│  - Download reports                                  │
└──────┬───────────────────────────────────────────────┘
       │
       ↓
┌──────────────────────────────────────────────────────┐
│                   AWS S3 Bucket                      │
│  uploads/        - PDF uploads                       │
│  temp/docParser/ - BDA processing output             │
│  reports/        - Generated PDF reports             │
└──────┬───────────────────────────────────────────────┘
       │
       ↓
┌──────────────────────────────────────────────────────┐
│        AWS Bedrock Data Automation (BDA)             │
│  - Extracts text from PDFs                           │
│  - Preserves document structure                      │
│  - Outputs to temp/docParser/                        │
└──────┬───────────────────────────────────────────────┘
       │
       ↓ (S3 Event Trigger)
       │
┌──────────────────────────────────────────────────────┐
│          Lambda: agent_trigger.py                    │
│  - Detects BDA completion                            │
│  - Triggers Keyword Generator Agent                  │
│  - Triggers Commercial Assessment Agent              │
└──────┬───────────────────────────────────────────────┘
       │
       ↓
┌──────────────────────────────────────────────────────┐
│     Bedrock Agent Core: Orchestrator                 │
│  - Routes requests to specialized agents             │
│  - Manages agent execution                           │
│  - Streams responses                                 │
└──────┬───────────────────────────────────────────────┘
       │
       ├─→ Keyword Generator Agent
       │   └─→ Claude 3.7 Sonnet
       │       └─→ DynamoDB: patent-keywords
       │
       ├─→ Commercial Assessment Agent
       │   └─→ Claude 3.7 Sonnet
       │       └─→ DynamoDB: early-commercial-assessment
       │
       ├─→ Patent Search Agent
       │   └─→ Claude 3.7 Sonnet
       │       └─→ Agent Core Gateway → PatentView API
       │           └─→ DynamoDB: patent-search-results
       │
       ├─→ Scholarly Article Agent
       │   └─→ Claude 3.7 Sonnet
       │       └─→ Agent Core Gateway → Semantic Scholar API
       │           └─→ DynamoDB: scholarly-articles-results
       │
       └─→ Report Generator
           └─→ ReportLab
               └─→ S3: reports/
```

## 🤖 Agent Details

### 1. Keyword Generator Agent

**Purpose:** Extract patent search keywords from invention disclosure

**Process:**

1. Reads BDA-processed document from S3
2. Analyzes invention like a patent examiner
3. Extracts structured data:
   - Title (concise invention name)
   - Technology Description (100-150 words)
   - Technology Applications (100-150 words)
   - Keywords (12-15 high-impact search terms)
4. Stores in DynamoDB

**Model:** Claude 3.7 Sonnet  
**Output:** `patent-keywords-{account}` table

---

### 2. Commercial Assessment Agent

**Purpose:** Evaluate commercialization potential and market viability

**Process:**

1. Reads same BDA output as keyword agent
2. Performs comprehensive analysis covering:
   - Problem Solved & Solution Offered
   - Non-Confidential Marketing Abstract
   - Technology Details
   - Potential Applications
   - Market Overview
   - Competition Analysis
   - Potential Licensees
   - Key Commercialization Challenges
   - Key Assumptions
   - Key Companies
3. Stores in DynamoDB

**Model:** Claude 3.7 Sonnet  
**Output:** `early-commercial-assessment-{account}` table  
**Trigger:** Automatic (after BDA completes)

---

### 3. Patent Search Agent

**Purpose:** Search USPTO PatentView database for prior art

**Process:**

1. Reads keywords from DynamoDB
2. Executes strategic searches via PatentView Gateway:
   - Searches each keyword (top 10 patents per keyword)
   - Deduplicates by patent_id
   - Pre-filters to top 50 by citation count
3. LLM evaluates each patent for relevance:
   - Technical overlap analysis
   - Novelty impact assessment
   - Generates relevance score (0-1.0)
4. Selects top 6 most relevant patents
5. Stores with comprehensive metadata

**Model:** Claude 3.7 Sonnet  
**Gateway:** PatentView API (OAuth2)  
**Output:** `patent-search-results-{account}` table  
**Trigger:** Manual (user-initiated)

---

### 4. Scholarly Article Agent

**Purpose:** Search Semantic Scholar for relevant academic papers

**Process:**

1. Reads keywords from DynamoDB
2. LLM generates 3-5 strategic search queries
3. Executes adaptive search with refinement:
   - Searches each query via Semantic Scholar Gateway
   - Assesses result quality
   - Refines queries if needed (max 3 attempts)
4. LLM evaluates each paper for relevance:
   - Technical overlap with invention
   - Problem domain similarity
   - Prior art potential
   - Relevance score (0-10)
5. Keeps only papers with score ≥7 and decision=KEEP
6. Returns top 8 papers

**Model:** Claude 3.7 Sonnet  
**Gateway:** Semantic Scholar API (OAuth2)  
**Output:** `scholarly-articles-results-{account}` table  
**Trigger:** Manual (user-initiated)

---

### 5. Report Generator

**Purpose:** Generate professional PDF assessment reports

**Process:**

1. Fetches data from all DynamoDB tables
2. Generates two separate PDF reports:
   - **Novelty Report:** Patent and article search results
   - **ECA Report:** Commercial assessment analysis
3. Uploads to S3 reports/ folder

**Technology:** ReportLab (Python PDF library)  
**Output:** S3 `reports/` folder  
**Trigger:** Manual (user-initiated)

## 📊 Data Storage

### DynamoDB Tables

| Table                                   | Partition Key | Sort Key      | Purpose                         |
| --------------------------------------- | ------------- | ------------- | ------------------------------- |
| `patent-keywords-{account}`             | pdf_filename  | timestamp     | Keywords and invention metadata |
| `patent-search-results-{account}`       | pdf_filename  | patent_number | USPTO patent search results     |
| `scholarly-articles-results-{account}`  | pdf_filename  | article_doi   | Academic paper search results   |
| `early-commercial-assessment-{account}` | pdf_filename  | timestamp     | Commercial assessment analysis  |

### S3 Bucket Structure

```
patent-novelty-pdf-processing-{account}/
├── uploads/                    # User PDF uploads
├── temp/docParser/            # BDA processing output
│   └── {filename-timestamp}/
│       └── result.json        # Extracted text
└── reports/                   # Generated PDF reports
    ├── {filename}_novelty_report.pdf
    └── {filename}_eca_report.pdf
```

## 🔄 Execution Flow

### Automatic Flow (After PDF Upload)

```
1. User uploads PDF to S3 uploads/
   ↓
2. S3 event triggers pdf_processor Lambda
   ↓
3. Lambda invokes BDA to extract text
   ↓
4. BDA processes PDF (~30 seconds)
   ↓
5. BDA outputs result.json to temp/docParser/
   ↓
6. S3 event triggers agent_trigger Lambda
   ↓
7. Lambda invokes Orchestrator twice:
   a) Keyword Generator Agent (auto)
   b) Commercial Assessment Agent (auto)
   ↓
8. Both agents run in parallel
   ↓
9. Results stored in DynamoDB
```

### Manual Flow (User-Triggered)

```
User triggers action via UI
   ↓
Frontend calls Orchestrator with action:
   - "search_patents"
   - "search_articles"
   - "generate_report"
   ↓
Orchestrator routes to appropriate agent
   ↓
Agent executes and stores results
   ↓
Frontend displays results
```

## 🔐 Security & Authentication

### Agent Core Gateway

- **PatentView Gateway:** OAuth2 client credentials flow
- **Semantic Scholar Gateway:** OAuth2 client credentials flow
- Environment variables store credentials securely

### IAM Roles

- **Lambda Execution Role:** BDA invocation, S3 access
- **Orchestrator Role:** Bedrock, S3, DynamoDB, ECR access

### Data Access

- All DynamoDB operations use IAM authentication
- S3 operations use IAM roles (no hardcoded credentials)

## 🚀 Deployment

### Prerequisites

- AWS Account with Bedrock access
- AWS CLI configured
- Node.js 20+ and npm
- Python 3.12+
- Docker

### Deploy Infrastructure

```bash
# Navigate to backend
cd backend

# Install dependencies
npm install

# Deploy CDK stack
npx cdk deploy
```

### Configure Agent Core Runtime

1. **Create Agent Runtime in AWS Console:**

   - Go to Bedrock → Agent Core
   - Create new runtime using Docker image URI from CDK output
   - Assign IAM role from CDK output

2. **Set Environment Variables:**

   ```
   AWS_REGION=us-west-2
   BUCKET_NAME=patent-novelty-pdf-processing-{account}
   KEYWORDS_TABLE_NAME=patent-keywords-{account}
   RESULTS_TABLE_NAME=patent-search-results-{account}
   ARTICLES_TABLE_NAME=scholarly-articles-results-{account}
   COMMERCIAL_ASSESSMENT_TABLE_NAME=early-commercial-assessment-{account}

   # PatentView Gateway
   PATENTVIEW_CLIENT_ID=your-client-id
   PATENTVIEW_CLIENT_SECRET=your-client-secret
   PATENTVIEW_TOKEN_URL=your-token-url
   PATENTVIEW_GATEWAY_URL=your-gateway-url

   # Semantic Scholar Gateway
   SEMANTIC_SCHOLAR_CLIENT_ID=your-client-id
   SEMANTIC_SCHOLAR_CLIENT_SECRET=your-client-secret
   SEMANTIC_SCHOLAR_TOKEN_URL=your-token-url
   SEMANTIC_SCHOLAR_GATEWAY_URL=your-gateway-url
   ```

3. **Update Lambda with Runtime ARN:**
   - Edit `backend/infrastructure/patent-novelty-stack.ts`
   - Update `AGENT_RUNTIME_ARN` with your runtime ARN
   - Redeploy: `npx cdk deploy`

### Create Agent Core Gateways

1. **PatentView Gateway:**

   - Use OpenAPI spec: `docs/patentview_openapi_spec.json`
   - Configure OAuth2 authentication

2. **Semantic Scholar Gateway:**
   - Use OpenAPI spec: `docs/semantic_scholar_openapi_spec.json`
   - Configure OAuth2 authentication

