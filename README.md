# Patent Novelty Assessment System

An intelligent patent novelty assessment platform built with AWS Bedrock, Agent Core, and deployed on AWS Lambda. The system provides automated prior art searches across patent databases and academic literature through AI-powered agents with comprehensive knowledge base integration.

![User Interface](./docs/media/user-interface.gif)

| Index                                               | Description                                             |
| :-------------------------------------------------- | :------------------------------------------------------ |
| [High Level Architecture](#high-level-architecture) | High level overview illustrating component interactions |
| [Deployment](#deployment-guide)                     | How to deploy the project                               |
| [User Guide](#user-guide)                           | The working solution                                    |
| [Directories](#directories)                         | General project directory structure                     |
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
│   ├── PatentNoveltyOrchestrator/
│   │   ├── orchestrator.py                    # Main orchestrator routing requests to agents
│   │   ├── keyword_agent.py                   # Extracts keywords from invention disclosures
│   │   ├── patent_search_agent.py             # Searches PatentView for prior art patents
│   │   ├── scholarly_article_agent.py         # Searches Semantic Scholar for academic papers
│   │   ├── commercial_assessment_agent.py     # Conducts early commercial assessment
│   │   ├── report_generator.py                # Generates professional PDF reports
│   │   ├── requirements.txt                   # Python dependencies
│   │   ├── Dockerfile                         # Container image for Agent Core Runtime
│   │   └── .dockerignore                      # Docker ignore file
│   ├── infrastructure/
│   │   ├── app.ts                             # CDK app entry point
│   │   └── patent-novelty-stack.ts            # Infrastructure as Code (CDK stack)
│   ├── lambda/
│   │   ├── pdf_processor.py                   # Triggers BDA processing on PDF upload
│   │   ├── agent_trigger.py                   # Triggers agents when BDA completes
│   │   ├── s3_api.py                          # S3 operations API Gateway
│   │   ├── dynamodb_api.py                    # DynamoDB operations API Gateway
│   │   └── agent_invoke_api.py                # Agent invocation API Gateway
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
│   ├── PatentView.txt                         # PatentView API documentation
│   ├── semantic_scholar_openapi_spec.json     # Semantic Scholar API specification
│   ├── semantic_scholar.json                  # Semantic Scholar API documentation
│   └── media/                                 # Images and diagrams for documentation
├── frontend/
│   ├── app/                                   # Next.js App Router pages
│   │   ├── favicon.ico                        # Site favicon
│   │   ├── globals.css                        # Global CSS styles
│   │   ├── layout.tsx                         # Root layout component
│   │   ├── page.tsx                           # Home page
│   │   ├── literature-search/page.tsx         # Literature search page
│   │   ├── patent-search/page.tsx             # Patent search page
│   │   ├── report-generation/page.tsx         # Report generation page
│   │   └── results/page.tsx                   # Results page
│   ├── components/                            # React components
│   │   ├── FileUploadCard.tsx                 # File upload component
│   │   ├── Header.tsx                         # Header component
│   │   ├── Keywords.tsx                       # Keywords display component
│   │   ├── LiteratureSearchResults.tsx        # Literature results component
│   │   ├── PatentSearchResults.tsx            # Patent results component
│   │   ├── UploadIcon.tsx                     # Upload icon component
│   │   ├── UploadSection.tsx                  # Upload section component
│   │   └── ui/                                # UI component library
│   │       └── button.tsx                     # Button component
│   ├── hooks/                                 # Custom React hooks
│   │   └── useFileUpload.ts                   # File upload hook
│   ├── lib/                                   # Utility functions and configuration
│   │   ├── config.ts                          # API configuration
│   │   ├── dynamodb.ts                        # DynamoDB operations
│   │   ├── patentSearch.ts                    # Patent search service
│   │   ├── reportGeneration.ts                # Report generation service
│   │   ├── scholarlySearch.ts                 # Scholarly search service
│   │   ├── statePersistence.ts                # State persistence utilities
│   │   └── utils.ts                           # General utilities
│   ├── types/                                 # TypeScript type definitions
│   │   └── index.ts                           # Type definitions
│   ├── public/                                # Static assets and images
│   │   ├── University_of_Minnesota_wordmark.ico
│   │   ├── University_of_Minnesota_wordmark.png
│   │   ├── file.svg                           # File icon
│   │   ├── globe.svg                          # Globe icon
│   │   ├── next.svg                           # Next.js logo
│   │   ├── vercel.svg                         # Vercel logo
│   │   └── window.svg                         # Window icon
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

## API Documentation

Here you can learn about the APIs the project uses:

- **External APIs**: [External API Documentation](./docs/APIdoc.md) - PatentView and Semantic Scholar APIs
- **Internal APIs**: [API Gateway Endpoints](./docs/API_GATEWAY_ENDPOINTS.md) - Internal API Gateway endpoints for frontend integration


## Credits

This application was architected and developed by <a href="https://www.linkedin.com/in/shaashvatm156/" target="_blank">Shaashvat Mittal</a>, <a href="https://www.linkedin.com/in/sahajpreet/" target="_blank">Sahajpreet Singh</a>, and <a href="https://www.linkedin.com/in/ashik-tharakan/" target="_blank">Ashik Tharakan</a>, with solutions architect <a href="https://www.linkedin.com/in/arunarunachalam/" target="_blank">Arun Arunachalam</a>, program manager <a href="https://www.linkedin.com/in/thomas-orr/" target="_blank">Thomas Orr</a> and product manager <a href="https://www.linkedin.com/in/rachelhayden/" target="_blank">Rachel Hayden</a>. Thanks to the ASU Cloud Innovation Center Technical and Project Management teams for their guidance and support.

## License

This project is distributed under the [MIT License](LICENSE).
