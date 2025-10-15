# Patent Novelty Assessment System

An AI-powered patent novelty assessment platform that automates prior art searches across patent databases and academic literature. The system analyzes invention disclosure documents, generates strategic search keywords, executes comprehensive searches, and produces professional PDF reports for patent examiners and technology transfer professionals.

![User Interface Demo](./docs/media/user-interface.gif)

> **[PLACEHOLDER]** Please provide a GIF or screenshot of the application interface and save it as `docs/media/user-interface.gif`

## Table of Contents

| Index                                                    | Description                                             |
| :------------------------------------------------------- | :------------------------------------------------------ |
| [High Level Architecture](#high-level-architecture)      | High level overview illustrating component interactions |
| [Deployment Guide](./docs/deploymentGuide.md)            | How to deploy the project                               |
| [User Guide](./docs/userGuide.md)                        | The working solution                                    |
| [Directories](#directories)                              | General project directory structure                     |
| [API Documentation](./docs/APIdoc.md)                    | Documentation on the APIs the project uses              |
| [Architecture Deep Dive](./docs/architectureDeepDive.md) | Technical architecture explanation                      |
| [Modification Guide](./docs/modificationGuide.md)        | Developer guide for extending/modifying                 |

## High-Level Architecture

The Patent Novelty Assessment System is a serverless, event-driven architecture built on AWS that orchestrates multiple AI agents to conduct comprehensive prior art searches. When a user uploads an invention disclosure PDF, the system automatically extracts content using Amazon Bedrock Data Automation (BDA), generates strategic search keywords, searches PatentView and Semantic Scholar databases, evaluates results using LLM-powered relevance scoring, and generates professional PDF reports.

For a detailed technical explanation of the architecture, see the [Architecture Deep Dive](./docs/architectureDeepDive.md).

![Architecture Diagram](./docs/media/architecture.png)

## Directories

```
├── backend/
│   ├── PatentNoveltyOrchestrator/
│   │   ├── orchestrator.py                    # Main orchestrator routing requests to agents
│   │   ├── keyword_agent.py                   # Extracts keywords from invention disclosures
│   │   ├── patent_search_agent.py             # Searches PatentView for prior art patents
│   │   ├── scholarly_article_agent.py         # Searches Semantic Scholar for academic papers
│   │   ├── commercial_assessment_agent.py     # Conducts early commercial assessment
│   │   ├── report_generator.py                # Generates professional PDF reports
│   │   ├── requirements.txt                   # Python dependencies
│   │   └── Dockerfile                         # Container image for Agent Core Runtime
│   ├── infrastructure/
│   │   ├── app.ts                             # CDK app entry point
│   │   └── patent-novelty-stack.ts            # Infrastructure as Code (CDK stack)
│   ├── lambda/
│   │   ├── pdf_processor.py                   # Triggers BDA processing on PDF upload
│   │   └── agent_trigger.py                   # Triggers agents when BDA completes
│   ├── cdk.json                               # CDK configuration
│   ├── package.json                           # Node.js dependencies
│   └── tsconfig.json                          # TypeScript configuration
├── docs/
│   ├── patentview_openapi_spec.json           # PatentView API specification
│   ├── semantic_scholar_openapi_spec.json     # Semantic Scholar API specification
│   └── media/                                 # Images and diagrams for documentation
├── deploy.sh                                  # Automated deployment script
├── LICENSE                                    # Project license
└── README.md                                  # This file
```

### Directory Explanations

1. **backend/PatentNoveltyOrchestrator/** - Contains all AI agent implementations using the Strands framework. The orchestrator routes requests to specialized agents (keyword extraction, patent search, article search, commercial assessment, report generation). Each agent uses AWS Bedrock Claude Sonnet 4.5 for LLM-powered analysis.

2. **backend/infrastructure/** - AWS CDK Infrastructure as Code defining all cloud resources: S3 buckets, Lambda functions, DynamoDB tables, IAM roles, and Docker image assets. The stack creates a complete serverless architecture.

3. **backend/lambda/** - Lambda functions that handle event-driven triggers: `pdf_processor.py` initiates BDA processing when PDFs are uploaded, and `agent_trigger.py` automatically invokes keyword and commercial assessment agents when BDA completes.

4. **docs/** - Contains OpenAPI specifications for external APIs (PatentView and Semantic Scholar) and media assets for documentation.

## Key Features

- **Automated Document Processing** - Uses Amazon Bedrock Data Automation to extract text from invention disclosure PDFs
- **AI-Powered Keyword Extraction** - Claude Sonnet 4.5 analyzes documents and generates strategic search keywords
- **Comprehensive Patent Search** - Searches PatentView database with intelligent query strategies and LLM-based relevance scoring
- **Academic Literature Search** - Searches Semantic Scholar with adaptive query refinement and semantic relevance evaluation
- **Early Commercial Assessment** - Analyzes market potential, competition, and commercialization viability
- **Professional PDF Reports** - Generates examiner-ready reports with prior art analysis and abstracts
- **Event-Driven Architecture** - Fully automated workflow from upload to report generation

## Technology Stack

- **AWS Bedrock** - Claude Sonnet 4.5 for LLM analysis, Data Automation for PDF processing
- **AWS Bedrock Agent Core** - Orchestrates multi-agent workflows with tool calling
- **AWS Lambda** - Serverless compute for event handling
- **Amazon S3** - Document storage and report delivery
- **Amazon DynamoDB** - NoSQL database for keywords, patents, articles, and assessments
- **AWS CDK** - Infrastructure as Code in TypeScript
- **Python 3.12** - Agent implementation with Strands framework
- **Docker** - Containerized agent runtime
- **PatentView API** - USPTO patent database access via MCP Gateway
- **Semantic Scholar API** - Academic paper search via MCP Gateway

## Credits

This application was architected and developed by <a href="https://www.linkedin.com/in/shaashvatm156/" target="_blank">Shaashvat Mittal</a>, <a href="https://www.linkedin.com/in/sahajpreet/" target="_blank">Sahajpreet Singh</a>, and <a href="https://www.linkedin.com/in/ashik-tharakan/" target="_blank">Ashik Tharakan</a>, with solutions architect <a href="https://www.linkedin.com/in/arunarunachalam/" target="_blank">Arun Arunachalam</a>, program manager <a href="https://www.linkedin.com/in/thomas-orr/" target="_blank">Thomas Orr</a> and product manager <a href="https://www.linkedin.com/in/rachelhayden/" target="_blank">Rachel Hayden</a>. Thanks to the ASU Cloud Innovation Center Technical and Project Management teams for their guidance and support.

## License

This project is licensed under the terms specified in the [LICENSE](./LICENSE) file.

---

_For detailed deployment instructions, see the [Deployment Guide](./docs/deploymentGuide.md)._

_For usage instructions, see the [User Guide](./docs/userGuide.md)._
