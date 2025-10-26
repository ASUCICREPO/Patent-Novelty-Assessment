# Patent Novelty Assessment System

An intelligent patent novelty assessment platform built with AWS Bedrock, Agent Core, and deployed on AWS Lambda. The system provides automated prior art searches across patent databases and academic literature through AI-powered agents with comprehensive knowledge base integration.

![User Interface](./docs/media/user-interface.gif)

| Index                                               | Description                                             |
| :-------------------------------------------------- | :------------------------------------------------------ |
| [High Level Architecture](#high-level-architecture) | High level overview illustrating component interactions |
| [Deployment](#deployment-guide)                     | How to deploy the project                               |
| [User Guide](#user-guide)                           | The working solution                                    |
| [Directories](#directories)                         | General project directory structure                     |
| [Key Features](#key-features)                       | Backend and frontend capabilities                       |
| [Technology Stack](#technology-stack)               | Technologies and frameworks used                        |
| [API Documentation](#api-documentation)             | Documentation on the API the project uses               |
| [Credits](#credits)                                 | Meet the team behind the solution                       |
| [License](#license)                                 | License details                                         |

## High-Level Architecture

The following architecture diagram illustrates the various AWS components utilized to deliver the solution. For an in-depth explanation of the backend, please look at the [Architecture Guide](docs/architectureDeepDive.md).

![Architecture Diagram](./docs/media/architecture.png)

## Deployment Guide

To deploy this solution, please follow the steps laid out in the [Deployment Guide](./docs/deploymentGuide.md).


## User Guide

Please refer to the [Web App User Guide](./docs/userGuide.md) for instructions on using the web app.

## Directories

```
├── backend/
│   ├── PatentNoveltyOrchestrator/             # AI agent implementations
│   ├── infrastructure/                        # CDK stacks and constructs
│   ├── lambda/                                # Lambda functions for API Gateway
│   ├── cdk.json                               # CDK configuration
│   ├── package.json                           # Node.js dependencies
│   ├── package-lock.json                      # Node.js dependency lock file
│   └── tsconfig.json                          # TypeScript configuration
├── docs/
│   ├── architectureDeepDive.md                # Technical architecture explanation
│   ├── deploymentGuide.md                     # Deployment instructions
│   ├── userGuide.md                           # User interface guide
│   ├── APIdoc.md                              # External API documentation
│   ├── API_GATEWAY_ENDPOINTS.md               # Internal API Gateway documentation
│   ├── modificationGuide.md                   # Developer modification guide
│   ├── patentview_openapi_spec.json           # PatentView API specification
│   ├── semantic_scholar_openapi_spec.json     # Semantic Scholar API specification
│   └── media/                                 # Images and diagrams for documentation
├── frontend/
│   ├── app/                                   # Next.js App Router pages
│   ├── components/                            # React components
│   ├── hooks/                                 # Custom React hooks
│   ├── lib/                                   # Utility functions and configuration
│   ├── types/                                 # TypeScript type definitions
│   ├── public/                                # Static assets and images
│   ├── .gitignore                             # Frontend git ignore file
│   ├── components.json                        # UI components configuration
│   ├── env.example                            # Environment variables template
│   ├── eslint.config.mjs                      # ESLint configuration
│   ├── next.config.ts                         # Next.js configuration
│   ├── package.json                           # Frontend dependencies
│   ├── package-lock.json                      # Frontend dependency lock file
│   ├── postcss.config.mjs                     # PostCSS configuration
│   └── tsconfig.json                          # TypeScript configuration
├── deploy.sh                                  # Automated deployment script
├── buildspec.yml                              # CodeBuild configuration
├── .gitignore                                 # Git ignore file
├── LICENSE                                    # Project license
└── README.md                                  # This file
```

1. **`backend/`**: AWS CDK app and backend code
   - `PatentNoveltyOrchestrator/`: AI agent implementations using Strands framework
   - `infrastructure/`: CDK stacks and constructs (infrastructure as code)
   - `lambda/`: Lambda functions for event handling and API Gateway
   - `cdk.json`: CDK configuration
   - `package.json` & `package-lock.json`: Node.js dependencies
   - `tsconfig.json`: TypeScript configuration
2. **`docs/`**: Architecture, deployment, and user guides with media assets
   - `architectureDeepDive.md`: Technical architecture explanation
   - `deploymentGuide.md`: Deployment instructions
   - `userGuide.md`: User interface guide
   - `APIdoc.md`: External API documentation
   - `API_GATEWAY_ENDPOINTS.md`: Internal API Gateway documentation
   - `modificationGuide.md`: Developer modification guide
   - API specifications and documentation files
3. **`frontend/`**: Next.js web application with API Gateway integration
   - `app/`: Next.js App Router configuration and pages
   - `components/`: Reusable UI components
     - `ui/`: UI component library (button.tsx, etc.)
   - `hooks/`: Custom React hooks for file upload and state management
   - `lib/`: Utility functions and API configuration
   - `types/`: TypeScript type definitions
   - `public/`: Static assets and images
   - `package.json` & `package-lock.json`: Frontend dependencies
   - Configuration files for Next.js, TypeScript, ESLint, and PostCSS
4. **Root**: Deployment scripts and build configurations
   - `deploy.sh`: Main deployment script (backend + frontend)
   - `buildspec.yml`: CodeBuild configuration for CI/CD
   - `.gitignore`: Git ignore file
   - `LICENSE`: Project license

## Key Features

### Backend Features
- **Automated Document Processing** - Uses Amazon Bedrock Data Automation to extract text from invention disclosure PDFs
- **AI-Powered Keyword Extraction** - Claude Sonnet 4.5 analyzes documents and generates strategic search keywords
- **Comprehensive Patent Search** - Searches PatentView database with intelligent query strategies and LLM-based relevance scoring
- **Academic Literature Search** - Searches Semantic Scholar with adaptive query refinement and semantic relevance evaluation
- **Early Commercial Assessment** - Analyzes market potential, competition, and commercialization viability
- **Professional PDF Reports** - Generates examiner-ready reports with prior art analysis and abstracts
- **Event-Driven Architecture** - Fully automated workflow from upload to report generation

### Frontend Features
- **Intuitive File Upload** - Drag-and-drop PDF upload with real-time progress tracking and validation
- **Multi-Page Workflow** - Guided user experience through upload, keyword review, patent search, literature search, and report generation
- **Interactive Results Display** - Dynamic tables showing patent and literature search results with filtering and selection capabilities
- **Status Monitoring** - Progress indicators and status updates throughout the analysis process
- **Keyword Management** - Editable keyword interface allowing users to refine search terms before analysis
- **Report Download Interface** - Direct download access to generated PTLS and ECA reports
- **State Persistence** - Browser-based state management ensuring progress is maintained across page refreshes

## Technology Stack

### Backend Technologies
- **AWS Bedrock** - Claude Sonnet 4.5 for LLM analysis, Data Automation for PDF processing
- **AWS Bedrock Agent Core** - Orchestrates multi-agent workflows with tool calling
- **AWS Lambda** - Serverless compute for event handling and API Gateway integration
- **Amazon S3** - Document storage and report delivery
- **Amazon DynamoDB** - NoSQL database for keywords, patents, articles, and assessments
- **AWS CDK** - Infrastructure as Code in TypeScript
- **Python 3.12** - Agent implementation with Strands framework
- **Docker** - Containerized agent runtime
- **PatentView API** - USPTO patent database access via MCP Gateway
- **Semantic Scholar API** - Academic paper search via MCP Gateway

### Frontend Technologies
- **Next.js 15** - React framework with App Router for server-side rendering and routing
- **React 19** - Modern React with concurrent features and improved performance
- **TypeScript** - Type-safe JavaScript for enhanced developer experience
- **Tailwind CSS** - Utility-first CSS framework for responsive design
- **shadcn/ui** - Modern component library built on Radix UI primitives
- **AWS SDK v3** - Direct integration with AWS services (S3, DynamoDB, Bedrock Agent Core)
- **Lucide React** - Icon library for consistent visual design
- **Custom Hooks** - React hooks for file upload, state management, and API integration

## API Documentation

Here you can learn about the APIs the project uses:

- **External APIs**: [External API Documentation](./docs/APIdoc.md) - PatentView and Semantic Scholar APIs
- **Internal APIs**: [API Gateway Endpoints](./docs/API_GATEWAY_ENDPOINTS.md) - Internal API Gateway endpoints for frontend integration


## Credits

This application was architected and developed by <a href="https://www.linkedin.com/in/shaashvatm156/" target="_blank">Shaashvat Mittal</a>, <a href="https://www.linkedin.com/in/sahajpreet/" target="_blank">Sahajpreet Singh</a>, and <a href="https://www.linkedin.com/in/ashik-tharakan/" target="_blank">Ashik Tharakan</a>, with solutions architect <a href="https://www.linkedin.com/in/arunarunachalam/" target="_blank">Arun Arunachalam</a>, program manager <a href="https://www.linkedin.com/in/thomas-orr/" target="_blank">Thomas Orr</a> and product manager <a href="https://www.linkedin.com/in/rachelhayden/" target="_blank">Rachel Hayden</a>. Thanks to the ASU Cloud Innovation Center Technical and Project Management teams for their guidance and support.

## License

This project is distributed under the [MIT License](LICENSE).
