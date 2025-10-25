# Patent Novelty Assessment - API Gateway Endpoints

This document provides comprehensive documentation for all internal API Gateway endpoints used by the Patent Novelty Assessment application. These endpoints power the frontend application and provide programmatic access to all system functionality.

## Base URL

```
https://your-api-id.execute-api.us-west-2.amazonaws.com/prod
```

## Authentication

**No authentication is required** for API Gateway endpoints. The API is publicly accessible without any authentication headers or API keys.

## Frontend Integration

The frontend application uses these endpoints through a centralized configuration system. All API calls are handled by utility functions in the `lib/` directory:

### Configuration

```typescript
// lib/config.ts
const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || '';

export function getApiUrl(endpoint: string): string {
  const cleanEndpoint = endpoint.startsWith('/') ? endpoint.slice(1) : endpoint;
  return API_BASE_URL ? `${API_BASE_URL}${cleanEndpoint}` : `/api/${cleanEndpoint}`;
}
```

### Usage Examples

```typescript
// File upload
const uploadUrl = await fetch(getApiUrl('/s3?operation=get_presigned_url&filename=test.pdf'));

// Query results
const patentResults = await fetch(getApiUrl('/dynamodb?tableType=patent-results&pdfFilename=test'));

// Trigger agent
const response = await fetch(getApiUrl('/agent-invoke'), {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ action: 'search_patents', pdfFilename: 'test' })
});
```

## Common Headers

All requests should include:
```
Content-Type: application/json
```

All responses include CORS headers:
```
Access-Control-Allow-Origin: *
Access-Control-Allow-Headers: Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token
Access-Control-Allow-Methods: GET,POST,PUT,DELETE,OPTIONS
```

## Error Responses

All endpoints return standardized error responses:

```json
{
  "error": "Error message",
  "details": "Additional error details"
}
```

**HTTP Status Codes:**
- `200` - Success
- `400` - Bad Request (invalid parameters)
- `404` - Not Found (resource doesn't exist in DynamoDB)
- `405` - Method Not Allowed (wrong HTTP method)
- `500` - Internal Server Error (Lambda function error)

---

## S3 Operations

### 1. Get Presigned Upload URL

**Endpoint:** `GET /s3?operation=get_presigned_url&filename=<filename>`

**Purpose:** Generate a presigned URL for direct S3 file upload to avoid API Gateway binary data corruption.

**Parameters:**
- `operation` (required): Must be `"get_presigned_url"`
- `filename` (required): Name of the file to upload (will be sanitized)

**Request Example:**
```bash
curl "https://your-api-id.execute-api.us-west-2.amazonaws.com/prod/s3?operation=get_presigned_url&filename=patent.pdf"
```

**Response:**
```json
{
  "uploadUrl": "https://bucket.s3.amazonaws.com/uploads/patent.pdf?X-Amz-Algorithm=...",
  "fileName": "patent.pdf",
  "s3Key": "uploads/patent.pdf",
  "bucket": "patent-novelty-pdf-processing-123456789"
}
```

**Response Fields:**
- `uploadUrl`: Presigned URL for direct S3 PUT operation (expires in 1 hour)
- `fileName`: Sanitized filename
- `s3Key`: S3 object key
- `bucket`: S3 bucket name

### 2. Check Report Status

**Endpoint:** `GET /s3?operation=check_reports&filename=<filename>`

**Purpose:** Check if PTLS and ECA reports are ready for download.

**Parameters:**
- `operation` (required): Must be `"check_reports"`
- `filename` (required): Base filename (without extension)

**Request Example:**
```bash
curl "https://your-api-id.execute-api.us-west-2.amazonaws.com/prod/s3?operation=check_reports&filename=patent"
```

**Response:**
```json
{
  "ptlsReady": true,
  "ecaReady": false,
  "filename": "patent"
}
```

**Response Fields:**
- `ptlsReady`: Boolean indicating if PTLS report is available
- `ecaReady`: Boolean indicating if ECA report is available
- `filename`: The checked filename

### 3. Get Report Download URLs

**Endpoint:** `GET /s3?operation=get_signed_urls&filename=<filename>`

**Purpose:** Get presigned download URLs for generated reports.

**Parameters:**
- `operation` (required): Must be `"get_signed_urls"`
- `filename` (required): Base filename (without extension)

**Request Example:**
```bash
curl "https://your-api-id.execute-api.us-west-2.amazonaws.com/prod/s3?operation=get_signed_urls&filename=patent"
```

**Response:**
```json
{
  "ptlsUrl": "https://bucket.s3.amazonaws.com/reports/patent_PTLS.pdf?X-Amz-Algorithm=...",
  "ecaUrl": "https://bucket.s3.amazonaws.com/reports/patent_ECA.pdf?X-Amz-Algorithm=...",
  "filename": "patent"
}
```

**Response Fields:**
- `ptlsUrl`: Presigned URL for PTLS report download (null if not ready)
- `ecaUrl`: Presigned URL for ECA report download (null if not ready)
- `filename`: The requested filename

---

## DynamoDB Operations

### 1. Query Patent Search Results

**Endpoint:** `GET /dynamodb?tableType=patent-results&pdfFilename=<filename>`

**Purpose:** Retrieve patent search results for a specific PDF analysis.

**Parameters:**
- `tableType` (required): Must be `"patent-results"`
- `pdfFilename` (required): PDF filename (without extension)

**Request Example:**
```bash
curl "https://your-api-id.execute-api.us-west-2.amazonaws.com/prod/dynamodb?tableType=patent-results&pdfFilename=patent"
```

**Response:**
```json
{
  "results": [
    {
      "publication_date": "2023-01-15",
      "citations": 25.0,
      "llm_examiner_notes": "Detailed relevance assessment...",
      "google_patents_url": "https://patents.google.com/patent/US12345678",
      "add_to_report": "No",
      "search_timestamp": "2025-01-23T10:30:00.000Z",
      "patent_title": "Example Patent Title",
      "publication_number": "12345678",
      "patent_number": "12345678",
      "patent_abstract": "Patent abstract text...",
      "matching_keywords": "keyword1,keyword2",
      "patent_inventors": "John Doe",
      "filing_date": "2022-06-15",
      "grant_date": "2023-01-15",
      "pdf_filename": "patent",
      "patent_assignees": "Example Corp",
      "relevance_score": 0.85,
      "backward_citations": 15.0
    }
  ],
  "count": 1
}
```

**Response Fields:**
- `result`: Single analysis object with metadata and keywords

### 2. Query Scholarly Article Results

**Endpoint:** `GET /dynamodb?tableType=scholarly-results&pdfFilename=<filename>`

**Purpose:** Retrieve scholarly article search results for a specific PDF analysis.

**Parameters:**
- `tableType` (required): Must be `"scholarly-results"`
- `pdfFilename` (required): PDF filename (without extension)

**Request Example:**
```bash
curl "https://your-api-id.execute-api.us-west-2.amazonaws.com/prod/dynamodb?tableType=scholarly-results&pdfFilename=patent"
```

**Response:**
```json
{
  "results": [
    {
      "paper_id": "abc123def456",
      "title": "Example Research Paper",
      "abstract": "Paper abstract text...",
      "authors": "Jane Smith, Bob Johnson",
      "venue": "Journal of Medical Devices",
      "year": 2023,
      "citation_count": 45,
      "url": "https://www.semanticscholar.org/paper/abc123def456",
      "fields_of_study": ["Medicine", "Engineering"],
      "publication_types": ["JournalArticle"],
      "open_access_pdf": {
        "url": "https://example.com/paper.pdf"
      },
      "matching_keywords": "medical device",
      "relevance_score": 0.92,
      "llm_examiner_notes": "Highly relevant to the invention...",
      "add_to_report": "Yes",
      "search_timestamp": "2025-01-23T10:35:00.000Z",
      "pdf_filename": "patent"
    }
  ],
  "count": 1
}
```

### 3. Get Analysis Results

**Endpoint:** `GET /dynamodb?tableType=analysis&fileName=<filename>`

**Purpose:** Retrieve analysis metadata and keywords for a specific PDF.

**Parameters:**
- `tableType` (required): Must be `"analysis"`
- `fileName` (required): PDF filename (without extension)

**Request Example:**
```bash
curl "https://your-api-id.execute-api.us-west-2.amazonaws.com/prod/dynamodb?tableType=analysis&fileName=patent"
```

**Response:**
```json
{
  "result": {
    "fileName": "patent",
    "keywords": "medical device,stent,deployment",
    "analysis_timestamp": "2025-01-23T10:00:00.000Z",
    "status": "completed",
    "patent_count": 8,
    "scholarly_count": 12
  }
}
```

### 4. Update Keywords

**Endpoint:** `PUT /dynamodb`

**Purpose:** Update keywords for a specific analysis.

**Request Body:**
```json
{
  "operation": "update_keywords",
  "fileName": "patent",
  "keywords": "updated,keyword,list"
}
```

**Response:**
```json
{
  "message": "Keywords updated successfully"
}
```

### 5. Update Add to Report Flag

**Endpoint:** `PUT /dynamodb`

**Purpose:** Update the "add_to_report" flag for a specific patent or scholarly result.

**Request Body:**
```json
{
  "operation": "update_add_to_report",
  "tableType": "patent-results",
  "pdfFilename": "patent",
  "publicationNumber": "12345678",
  "addToReport": "Yes"
}
```

**Response:**
```json
{
  "message": "Updated add_to_report for patent 12345678 to Yes"
}
```

---

## Agent Invoke Operations

### 1. Trigger Patent Search

**Endpoint:** `POST /agent-invoke`

**Purpose:** Trigger Bedrock Agent to perform patent search analysis.

**Request Body:**
```json
{
  "action": "search_patents",
  "pdfFilename": "patent"
}
```

**Response:**
```json
{
  "sessionId": "patent-search-1761200173183-bdnj5qmg6",
  "action": "search_patents",
  "message": "Patent search triggered successfully",
  "status": "processing"
}
```

**Response Fields:**
- `sessionId`: Unique session identifier for tracking
- `action`: The triggered action
- `message`: Status message
- `status`: Current processing status

### 2. Trigger Scholarly Search

**Endpoint:** `POST /agent-invoke`

**Purpose:** Trigger Bedrock Agent to perform scholarly article search analysis.

**Request Body:**
```json
{
  "action": "search_articles",
  "pdfFilename": "patent"
}
```

**Response:**
```json
{
  "sessionId": "scholarly-search-1761200173183-xyz789",
  "action": "search_articles",
  "message": "Scholarly search triggered successfully",
  "status": "processing"
}
```

### 3. Trigger Report Generation

**Endpoint:** `POST /agent-invoke`

**Purpose:** Trigger Bedrock Agent to generate PTLS and ECA reports.

**Request Body:**
```json
{
  "action": "generate_report",
  "pdfFilename": "patent"
}
```

**Response:**
```json
{
  "sessionId": "report-generation-1761200173183-abc123",
  "action": "generate_report",
  "message": "Report generation triggered successfully",
  "status": "processing"
}
```

---

## File Upload Process

The application uses a **two-step process** for file uploads to avoid API Gateway binary data corruption:

### Step 1: Request Presigned URL
```javascript
const response = await fetch(`${apiBaseUrl}/s3?operation=get_presigned_url&filename=${filename}`);
const { uploadUrl, fileName, s3Key, bucket } = await response.json();
```

### Step 2: Direct S3 Upload
```javascript
const uploadResponse = await fetch(uploadUrl, {
  method: 'PUT',
  body: file,
  headers: {
    'Content-Type': 'application/pdf'
  }
});
```

This approach ensures files are uploaded without corruption and bypasses API Gateway's binary data handling limitations.

---

## Rate Limiting

- **No explicit rate limits** are enforced by the API Gateway
- **Lambda concurrency limits** apply (default: 1000 concurrent executions)
- **DynamoDB throttling** may occur under high load
- **S3 operations** are generally not rate-limited

## Monitoring and Logging

All API calls are logged in **AWS CloudWatch**:
- **API Gateway Logs**: Request/response details, latency, errors
- **Lambda Logs**: Function execution logs, errors, performance metrics
- **CloudWatch Metrics**: Request count, latency, error rates

## Error Handling

The system implements automatic retry logic for:
- Network timeouts
- Lambda function errors
- DynamoDB throttling
- S3 service errors

**Recommended retry strategy:**
- Maximum 3 retries
- Exponential backoff (1s, 2s, 4s)
- Retry on 5xx errors only

## Security Considerations

- **No AWS credentials** exposed to frontend
- **IAM roles** with least privilege access
- **CORS enabled** for all origins (configure as needed for production)
- **S3 presigned URLs** expire after 1 hour
- **Lambda functions** run in VPC (if configured)

## Testing

### Complete Endpoint Testing (Execution Flow Order)

Use these comprehensive curl examples to test all endpoints in the order they would be executed:

#### Step 1: File Upload

**1. Get Presigned Upload URL**
```bash
curl "https://your-api-id.execute-api.us-west-2.amazonaws.com/prod/s3?operation=get_presigned_url&filename=invention.pdf"
```

**2. Direct File Upload (POST)**
```bash
curl -X POST "https://your-api-id.execute-api.us-west-2.amazonaws.com/prod/s3?filename=invention.pdf" \
  -H "Content-Type: application/pdf" \
  --data-binary @invention.pdf
```

**⚠️ Important Note**: After uploading a file, wait for the system to process it (keyword extraction, patent search, literature search) before testing the following endpoints. This typically takes 25-30 minutes.

#### Step 2: Check Processing Results & Update Results (All Can Be Done in Parallel)

**3. Get Analysis Results (Keywords)**
```bash
curl "https://your-api-id.execute-api.us-west-2.amazonaws.com/prod/dynamodb?tableType=analysis&fileName=invention"
```

**4. Update Keywords (Optional - can be done immediately after getting analysis results)**
```bash
curl -X PUT "https://your-api-id.execute-api.us-west-2.amazonaws.com/prod/dynamodb" \
  -H "Content-Type: application/json" \
  -d '{
    "operation": "update_keywords",
    "tableType": "analysis",
    "fileName": "invention",
    "keywords": ["medical device", "stent", "deployment"]
  }'
```

**5. Get Patent Search Results**
```bash
curl "https://your-api-id.execute-api.us-west-2.amazonaws.com/prod/dynamodb?tableType=patent-results&pdfFilename=invention"
```

**6. Update Patent Add to Report Flag (Optional - can be done immediately after getting patent results)**
```bash
curl -X PUT "https://your-api-id.execute-api.us-west-2.amazonaws.com/prod/dynamodb" \
  -H "Content-Type: application/json" \
  -d '{
    "operation": "update_add_to_report",
    "tableType": "patent-results",
    "pdfFilename": "invention",
    "patentNumber": "12345678",
    "addToReport": true
  }'
```

**7. Get Scholarly Article Results**
```bash
curl "https://your-api-id.execute-api.us-west-2.amazonaws.com/prod/dynamodb?tableType=scholarly-results&pdfFilename=invention"
```

**8. Update Scholarly Article Add to Report Flag (Optional - can be done immediately after getting scholarly results)**
```bash
curl -X PUT "https://your-api-id.execute-api.us-west-2.amazonaws.com/prod/dynamodb" \
  -H "Content-Type: application/json" \
  -d '{
    "operation": "update_add_to_report",
    "tableType": "scholarly-results",
    "pdfFilename": "invention",
    "articleDoi": "10.1000/182",
    "addToReport": true
  }'
```

#### Step 3: Trigger Additional Processing (Optional)

**9. Trigger Patent Search**
```bash
curl -X POST "https://your-api-id.execute-api.us-west-2.amazonaws.com/prod/agent-invoke" \
  -H "Content-Type: application/json" \
  -d '{"action": "search_patents", "pdfFilename": "invention"}'
```

**10. Trigger Scholarly Search**
```bash
curl -X POST "https://your-api-id.execute-api.us-west-2.amazonaws.com/prod/agent-invoke" \
  -H "Content-Type: application/json" \
  -d '{"action": "search_articles", "pdfFilename": "invention"}'
```

**11. Trigger Report Generation**
```bash
curl -X POST "https://your-api-id.execute-api.us-west-2.amazonaws.com/prod/agent-invoke" \
  -H "Content-Type: application/json" \
  -d '{"action": "generate_report", "pdfFilename": "invention"}'
```

#### Step 5: Check and Download Reports

**12. Check Report Status**
```bash
curl "https://your-api-id.execute-api.us-west-2.amazonaws.com/prod/s3?operation=check_reports&filename=invention"
```

**13. Get Report Download URLs**
```bash
curl "https://your-api-id.execute-api.us-west-2.amazonaws.com/prod/s3?operation=get_signed_urls&filename=invention"
```

### Error Testing

**Test Invalid Parameters:**
```bash
# Missing required parameters
curl "https://your-api-id.execute-api.us-west-2.amazonaws.com/prod/s3?operation=get_presigned_url"
curl "https://your-api-id.execute-api.us-west-2.amazonaws.com/prod/dynamodb?tableType=patent-results"

# Invalid operation
curl "https://your-api-id.execute-api.us-west-2.amazonaws.com/prod/s3?operation=invalid&filename=test.pdf"
# Expected response: {"error": "Invalid operation. Must be: get_signed_urls, check_reports, or get_presigned_url"}

# Invalid table type
curl "https://your-api-id.execute-api.us-west-2.amazonaws.com/prod/dynamodb?tableType=invalid&pdfFilename=test"
# Expected response: {"error": "Invalid tableType. Must be: analysis, patent-results, or scholarly-results"}

# Invalid action
curl -X POST "https://your-api-id.execute-api.us-west-2.amazonaws.com/prod/agent-invoke" \
  -H "Content-Type: application/json" \
  -d '{"action": "invalid_action", "pdfFilename": "test"}'
# Expected response: {"error": "Invalid action. Must be one of: search_patents, search_articles, generate_report"}
```

### Testing with Postman

Import these requests into Postman:

**Collection JSON:**
```json
{
  "info": {
    "name": "Patent Novelty Assessment API",
    "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
  },
  "item": [
    {
      "name": "S3 - Get Presigned URL",
      "request": {
        "method": "GET",
        "header": [],
        "url": {
          "raw": "{{baseUrl}}/s3?operation=get_presigned_url&filename=invention.pdf",
          "host": ["{{baseUrl}}"],
          "path": ["s3"],
          "query": [
            {"key": "operation", "value": "get_presigned_url"},
            {"key": "filename", "value": "invention.pdf"}
          ]
        }
      }
    },
    {
      "name": "DynamoDB - Get Patent Results",
      "request": {
        "method": "GET",
        "header": [],
        "url": {
          "raw": "{{baseUrl}}/dynamodb?tableType=patent-results&pdfFilename=invention",
          "host": ["{{baseUrl}}"],
          "path": ["dynamodb"],
          "query": [
            {"key": "tableType", "value": "patent-results"},
            {"key": "pdfFilename", "value": "invention"}
          ]
        }
      }
    },
    {
      "name": "Agent - Trigger Patent Search",
      "request": {
        "method": "POST",
        "header": [
          {"key": "Content-Type", "value": "application/json"}
        ],
        "body": {
          "mode": "raw",
          "raw": "{\n  \"action\": \"search_patents\",\n  \"pdfFilename\": \"invention\"\n}"
        },
        "url": {
          "raw": "{{baseUrl}}/agent-invoke",
          "host": ["{{baseUrl}}"],
          "path": ["agent-invoke"]
        }
      }
    }
  ],
  "variable": [
    {
      "key": "baseUrl",
      "value": "https://your-api-id.execute-api.us-west-2.amazonaws.com/prod"
    }
  ]
}
```

### Expected Response Codes

- **200**: Success
- **400**: Bad Request (missing/invalid parameters)
- **405**: Method Not Allowed (wrong HTTP method)
- **500**: Internal Server Error (Lambda function error)

### Testing Checklist

- [ ] All S3 operations (4 endpoints)
- [ ] All DynamoDB GET operations (3 endpoints)
- [ ] All DynamoDB PUT operations (2 endpoints)
- [ ] All Agent Invoke operations (3 endpoints)
- [ ] Error scenarios with invalid parameters
- [ ] File upload with actual PDF file
- [ ] Response validation against documented schemas
