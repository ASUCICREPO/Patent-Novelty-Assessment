# Project Modification Guide

## Introduction

This guide is for developers who want to extend, customize, or modify the Patent Novelty Assessment System. The system is built with modularity in mind, making it straightforward to add new agents, modify search strategies, customize reports, or integrate additional data sources.

## Extending Agent Functionality

### Adding a New Agent

To add a new specialized agent to the system:

**1. Create the Agent File**

Create a new Python file in `backend/PatentNoveltyOrchestrator/`:

```python
#!/usr/bin/env python3
"""
Your New Agent
Description of what this agent does.
"""
import json
import os
import boto3
from datetime import datetime
from typing import Dict, Any
from strands import Agent, tool

# Environment Variables
AWS_REGION = os.getenv('AWS_REGION', 'us-west-2')
YOUR_TABLE = os.getenv('YOUR_TABLE_NAME')

# Define your tools
@tool
def your_tool_function(param1: str, param2: Dict[str, Any]) -> str:
    """
    Tool description for the LLM.
    """
    try:
        # Your tool logic here
        return "Success message"
    except Exception as e:
        return f"Error: {str(e)}"

# Define the agent
your_new_agent = Agent(
    model="global.anthropic.claude-sonnet-4-5-20250929-v1:0",
    tools=[your_tool_function],
    system_prompt="""You are an expert in [domain].
    
    Your mission is to [describe mission].
    
    WORKFLOW:
    1. Step one
    2. Step two
    3. Step three
    
    OUTPUT FORMAT:
    [Describe expected output format]
    """
)
```

**2. Register Agent in Orchestrator**

Edit `backend/PatentNoveltyOrchestrator/orchestrator.py`:

```python
# Add import at top
from your_new_agent import your_new_agent

# Add handler function
async def handle_your_new_action(payload):
    """Handle your new action requests."""
    print("Orchestrator: Routing to Your New Agent")
    
    # Extract parameters from payload
    param1 = payload.get("param1")
    
    if not param1:
        yield {"error": "Error: 'param1' is required"}
        return
    
    # Create enhanced prompt
    enhanced_prompt = f"""Your instructions for the agent with {param1}"""
    
    try:
        full_response = ""
        async for event in your_new_agent.stream_async(enhanced_prompt):
            if "data" in event:
                full_response += event["data"]
            elif "current_tool_use" in event:
                yield {"tool_name": event["current_tool_use"]["name"], "agent": "your_new_agent"}
            elif "error" in event:
                yield {"error": event["error"]}
                return
        
        if full_response.strip():
            yield {"response": full_response, "agent": "your_new_agent"}
        else:
            yield {"error": "No response generated"}
                
    except Exception as e:
        yield {"error": f"Error: {str(e)}"}

# Add to main orchestrator routing
async def handle_orchestrator_request(payload):
    action = payload.get("action")
    
    # Add your new action
    if action == "your_new_action":
        async for event in handle_your_new_action(payload):
            yield event
    # ... existing actions ...
```

**3. Add DynamoDB Table (if needed)**

Edit `backend/infrastructure/patent-novelty-stack.ts`:

```typescript
// Add new DynamoDB table
const yourNewTable = new dynamodb.Table(this, "YourNewTable", {
  tableName: `your-new-table-${accountId}`,
  partitionKey: {
    name: "pdf_filename",
    type: dynamodb.AttributeType.STRING,
  },
  sortKey: { name: "timestamp", type: dynamodb.AttributeType.STRING },
  removalPolicy: cdk.RemovalPolicy.DESTROY,
  billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
});

// Add table permissions to agent role
new iam.PolicyStatement({
  effect: iam.Effect.ALLOW,
  actions: [
    "dynamodb:PutItem",
    "dynamodb:GetItem",
    "dynamodb:UpdateItem",
    "dynamodb:Query",
    "dynamodb:Scan",
  ],
  resources: [
    yourNewTable.tableArn,
  ],
})

// Add output
new cdk.CfnOutput(this, "YourNewTableName", {
  value: yourNewTable.tableName,
  description: "DynamoDB table for your new data",
});
```

**4. Update Requirements**

Add any new Python dependencies to `backend/PatentNoveltyOrchestrator/requirements.txt`.

**5. Redeploy**

```bash
cd backend
npx cdk deploy
```

## Modifying Search Strategies

### Customizing Patent Search

Edit `backend/PatentNoveltyOrchestrator/patent_search_agent.py`:

**Change Pre-filter Count:**
```python
# Line ~200
top_patents = prefilter_by_citations(unique_patents, top_n=100)  # Increase from 50
```

**Modify LLM Relevance Threshold:**
```python
# In store_patentview_analysis tool
if llm_evaluation['overall_relevance_score'] >= 0.6:  # Lower from 0.7 for more results
    patent['add_to_report'] = 'Yes'
```

**Add Custom Query Strategies:**
```python
@tool
def search_patents_custom_strategy(keywords_string: str) -> Dict[str, Any]:
    """Your custom search strategy."""
    # Parse keywords
    keywords = [k.strip() for k in keywords_string.split(',')]
    
    # Build custom query
    query_json = {
        "_and": [
            {"_text_any": {"patent_abstract": keywords[0]}},
            {"_text_any": {"patent_title": keywords[1]}}
        ]
    }
    
    # Execute search
    result = run_patentview_search_via_gateway(query_json, limit=20)
    return result
```

### Customizing Article Search

Edit `backend/PatentNoveltyOrchestrator/scholarly_article_agent.py`:

**Change Number of Search Queries:**
```python
# In search_semantic_scholar_articles_strategic tool
# Modify LLM prompt to generate more/fewer queries
"Generate 7 strategic search queries..."  # Increase from 5
```

**Adjust Relevance Score Threshold:**
```python
# In evaluate_paper_relevance_with_llm_internal function
if relevance_assessment['relevance_score'] >= 6:  # Lower from 7
    relevance_assessment['decision'] = 'KEEP'
```

**Modify Query Refinement Logic:**
```python
# In assess_search_result_quality function
if total_results > 5000:  # Lower threshold from 10000
    return {
        'action': 'refine',
        'reason': 'Too many results - query is too broad'
    }
```

## Customizing Report Generation

### Modifying Report Layout

Edit `backend/PatentNoveltyOrchestrator/report_generator.py`:

**Change Report Title:**
```python
# Line ~150
story.append(Paragraph("Your Custom Report Title", title_style))
```

**Add New Sections:**
```python
# After existing sections, before legal notice
story.append(Paragraph("Your New Section", heading_style))
story.append(Paragraph("Your section content here", styles['Normal']))
```

**Modify Table Columns:**
```python
# Patent table (line ~200)
patent_table_data = [[
    Paragraph('#', header_style),
    Paragraph('Number', header_style),
    Paragraph('Your New Column', header_style),  # Add column
    # ... existing columns
]]

# Adjust column widths
patent_table = Table(patent_table_data, colWidths=[0.3*inch, 0.9*inch, 1.0*inch, ...])
```

**Change Report Styling:**
```python
# Modify custom styles (line ~140)
title_style = ParagraphStyle(
    'CustomTitle',
    parent=styles['Heading1'],
    fontSize=20,  # Increase from 18
    textColor=colors.HexColor('#0066cc'),  # Change color
    spaceAfter=10,  # Increase spacing
    alignment=TA_CENTER
)
```

### Adding Report Filters

```python
def _fetch_patent_results(self) -> List[Dict[str, Any]]:
    """Fetch patents with custom filters."""
    # ... existing code ...
    
    # Add custom filter
    patents_filtered = [
        p for p in patents_for_report 
        if float(p.get('relevance_score', 0)) >= 0.8  # Only high-relevance
        and int(p.get('citation_count', 0)) >= 10  # Only well-cited
    ]
    
    return patents_filtered[:8]
```

## Adding New Data Sources

### Integrating a New API

**1. Create OpenAPI Specification**

Create `docs/your_api_openapi_spec.json` with your API definition.

**2. Create MCP Gateway**

Follow Pre-Deployment Step 5/6 in the Deployment Guide to create an MCP Gateway for your API.

**3. Create Agent with API Tools**

```python
from strands.tools.mcp.mcp_client import MCPClient
from mcp.client.streamable_http import streamablehttp_client

# Gateway configuration
YOUR_API_CLIENT_ID = os.environ.get('YOUR_API_CLIENT_ID')
YOUR_API_CLIENT_SECRET = os.environ.get('YOUR_API_CLIENT_SECRET')
YOUR_API_TOKEN_URL = os.environ.get('YOUR_API_TOKEN_URL')
YOUR_API_GATEWAY_URL = os.environ.get('YOUR_API_GATEWAY_URL')

def fetch_your_api_access_token():
    """Get OAuth access token."""
    response = requests.post(
        YOUR_API_TOKEN_URL,
        data=f"grant_type=client_credentials&client_id={YOUR_API_CLIENT_ID}&client_secret={YOUR_API_CLIENT_SECRET}",
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
        timeout=30
    )
    return response.json().get('access_token')

@tool
def search_your_api(query: str) -> Dict[str, Any]:
    """Search your API."""
    access_token = fetch_your_api_access_token()
    mcp_client = MCPClient(lambda: create_streamable_http_transport(YOUR_API_GATEWAY_URL, access_token))
    
    with mcp_client:
        tools = get_full_tools_list(mcp_client)
        search_tool = tools[0]  # Find your tool
        
        result = mcp_client.call_tool_sync(
            name=search_tool.tool_name,
            arguments={"query": query},
            tool_use_id=f"search-{hash(query)}"
        )
        
        return result
```

**4. Add Environment Variables**

Add to Agent Core Runtime configuration:
- `YOUR_API_CLIENT_ID`
- `YOUR_API_CLIENT_SECRET`
- `YOUR_API_TOKEN_URL`
- `YOUR_API_GATEWAY_URL`

## Modifying Frontend Integration

### Adding a Web Interface

The current system uses S3 for file upload. To add a web interface:

**1. Create Frontend Application**

```bash
# Create React app
npx create-react-app frontend
cd frontend
npm install aws-sdk axios
```

**2. Add Upload Component**

```javascript
import AWS from 'aws-sdk';

const s3 = new AWS.S3({
  region: 'us-west-2',
  credentials: new AWS.CognitoIdentityCredentials({
    IdentityPoolId: 'YOUR_IDENTITY_POOL_ID'
  })
});

function UploadComponent() {
  const handleUpload = async (file) => {
    const params = {
      Bucket: 'patent-novelty-pdf-processing-ACCOUNT_ID',
      Key: `uploads/${file.name}`,
      Body: file
    };
    
    await s3.upload(params).promise();
    alert('Upload successful!');
  };
  
  return (
    <input type="file" onChange={(e) => handleUpload(e.target.files[0])} />
  );
}
```

**3. Add Status Monitoring**

```javascript
const checkStatus = async (filename) => {
  const dynamodb = new AWS.DynamoDB.DocumentClient();
  
  const params = {
    TableName: 'patent-keywords-ACCOUNT_ID',
    KeyConditionExpression: 'pdf_filename = :filename',
    ExpressionAttributeValues: {
      ':filename': filename
    }
  };
  
  const result = await dynamodb.query(params).promise();
  return result.Items[0]?.processing_status;
};
```

### Adding API Gateway for Frontend

**1. Create API Gateway**

Edit `backend/infrastructure/patent-novelty-stack.ts`:

```typescript
import * as apigateway from 'aws-cdk-lib/aws-apigateway';

// Create API Gateway
const api = new apigateway.RestApi(this, 'PatentNoveltyApi', {
  restApiName: 'Patent Novelty API',
  description: 'API for Patent Novelty Assessment',
  defaultCorsPreflightOptions: {
    allowOrigins: apigateway.Cors.ALL_ORIGINS,
    allowMethods: apigateway.Cors.ALL_METHODS,
  },
});

// Add endpoints
const upload = api.root.addResource('upload');
upload.addMethod('POST', new apigateway.LambdaIntegration(uploadFunction));

const status = api.root.addResource('status');
status.addMethod('GET', new apigateway.LambdaIntegration(statusFunction));
```

**2. Create Lambda Functions**

Create `backend/lambda/api_upload.py` and `backend/lambda/api_status.py` for API endpoints.

## Database Schema Modifications

### Adding Fields to DynamoDB Tables

**1. Update Agent Code**

Edit the agent that writes to the table (e.g., `keyword_agent.py`):

```python
@tool
def store_keywords_in_dynamodb(pdf_filename: str, keywords_response: str) -> str:
    # ... existing code ...
    
    item = {
        'pdf_filename': pdf_filename,
        'timestamp': timestamp,
        # ... existing fields ...
        'your_new_field': 'your_value',  # Add new field
        'another_field': 123
    }
    
    table.put_item(Item=item)
```

**2. Update Report Generator**

Edit `backend/PatentNoveltyOrchestrator/report_generator.py`:

```python
def _fetch_keywords_data(self) -> Dict[str, Any]:
    # ... existing code ...
    
    return {
        'title': item.get('title', 'Unknown Title'),
        # ... existing fields ...
        'your_new_field': item.get('your_new_field', 'Default value')
    }
```

No schema migration needed - DynamoDB is schemaless!

## Testing Modifications

### Unit Testing Agents

Create `backend/PatentNoveltyOrchestrator/tests/test_your_agent.py`:

```python
import pytest
from your_agent import your_tool_function

def test_your_tool():
    result = your_tool_function("test_param", {"key": "value"})
    assert "Success" in result

def test_your_tool_error_handling():
    result = your_tool_function(None, {})
    assert "Error" in result
```

Run tests:
```bash
cd backend/PatentNoveltyOrchestrator
pip install pytest
pytest tests/
```

### Integration Testing

Test the full workflow:

```bash
# Upload test PDF
aws s3 cp test.pdf s3://patent-novelty-pdf-processing-ACCOUNT_ID/uploads/

# Monitor logs
aws logs tail /aws/lambda/PatentNoveltyStack-PdfProcessorFunction --follow

# Check DynamoDB
aws dynamodb scan --table-name patent-keywords-ACCOUNT_ID --limit 1

# Verify reports
aws s3 ls s3://patent-novelty-pdf-processing-ACCOUNT_ID/reports/
```

## Best Practices

### Code Organization
- Keep agents focused on single responsibilities
- Use descriptive function and variable names
- Add comprehensive docstrings to all tools
- Follow Python PEP 8 style guidelines

### Error Handling
- Always wrap tool logic in try-except blocks
- Return descriptive error messages
- Log errors for debugging
- Implement retry logic for external API calls

### Performance Optimization
- Use DynamoDB batch operations for multiple items
- Implement caching for frequently accessed data
- Use async/await for concurrent operations
- Monitor CloudWatch metrics for bottlenecks

### Security
- Never hardcode credentials in code
- Use environment variables for sensitive data
- Implement least-privilege IAM policies
- Validate all user inputs

### Documentation
- Update this guide when adding new features
- Document all environment variables
- Maintain OpenAPI specs for new APIs
- Add inline comments for complex logic

## Conclusion

The Patent Novelty Assessment System is designed to be extensible and customizable. By following the patterns established in the existing code, you can easily add new agents, modify search strategies, customize reports, and integrate additional data sources.

For questions or contributions, please refer to the project repository and contribution guidelines.
