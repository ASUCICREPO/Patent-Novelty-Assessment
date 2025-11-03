# Patent Novelty Assessment APIs

This document describes the external APIs used by the Patent Novelty Assessment System.

## Base URLs

The system integrates with two external APIs via AWS Bedrock MCP Gateways:

## 1) PatentView Patent Search API

The PatentView API provides access to USPTO patent data including granted patents, patent applications, inventors, assignees, and citations.

### Authentication

- **Type**: OAuth 2.0 Client Credentials
- **Token URL**: Configured in MCP Gateway
- **Credentials**: Client ID and Client Secret stored in Agent Core Runtime environment variables

### Endpoints

#### POST /patents/query — Search Patents

Search for patents using structured queries with field-specific filters.

- **Purpose**: Execute complex patent searches with multiple criteria
- **Request body**:
```json
{
  "q": {
    "_text_any": {
      "patent_abstract": "keyword1 keyword2"
    }
  },
  "f": [
    "patent_id",
    "patent_title",
    "patent_abstract",
    "patent_date",
    "patent_num_times_cited_by_us_patents",
    "inventors.inventor_name_first",
    "inventors.inventor_name_last",
    "assignees.assignee_organization"
  ],
  "o": {
    "size": 10
  },
  "s": [
    {
      "patent_date": "desc"
    }
  ]
}
```
- **Response**: JSON object containing array of patents with requested fields

**Query Operators:**
- `_text_any`: Matches any of the specified terms (OR logic)
- `_text_all`: Matches all specified terms (AND logic)
- `_text_phrase`: Matches exact phrase
- `_eq`: Equals
- `_neq`: Not equals
- `_gt`: Greater than
- `_gte`: Greater than or equal
- `_lt`: Less than
- `_lte`: Less than or equal

**Available Fields:**
- `patent_id`: Patent number (e.g., "10123456")
- `patent_title`: Patent title
- `patent_abstract`: Patent abstract text
- `patent_date`: Grant date (YYYY-MM-DD)
- `patent_num_times_cited_by_us_patents`: Forward citations count
- `patent_num_us_patents_cited`: Backward citations count
- `patent_num_foreign_documents_cited`: Foreign citations count
- `inventors.inventor_name_first`: Inventor first name
- `inventors.inventor_name_last`: Inventor last name
- `assignees.assignee_organization`: Assignee organization name
- `assignees.assignee_individual_name_first`: Individual assignee first name
- `assignees.assignee_individual_name_last`: Individual assignee last name

**Sort Options:**
- `patent_date`: Sort by grant date (asc/desc)
- `patent_num_times_cited_by_us_patents`: Sort by citation count (asc/desc)

**Pagination:**
- `o.size`: Number of results to return (max 100)
- `o.page`: Page number (1-indexed)

## 2) Semantic Scholar Academic Paper Search API

The Semantic Scholar API provides access to 200M+ research papers with metadata, abstracts, citations, and author information.

### Authentication

- **Type**: OAuth 2.0 Client Credentials
- **Token URL**: Configured in MCP Gateway
- **Credentials**: Client ID and Client Secret stored in Agent Core Runtime environment variables

### Endpoints

#### POST /paper/search — Search Academic Papers

Search for research papers using keyword queries.

- **Purpose**: Find relevant academic papers for prior art assessment
- **Request body**:
```json
{
  "query": "machine learning neural networks",
  "limit": 30,
  "fields": "title,abstract,authors,venue,year,citationCount,url,fieldsOfStudy,publicationTypes,openAccessPdf,referenceCount"
}
```
- **Response**: JSON object containing array of papers with requested fields

**Query Parameters:**
- `query` (required): Search query string (plain text, space-separated terms)
- `limit` (optional): Number of results to return (default: 10, max: 100)
- `fields` (optional): Comma-separated list of fields to return

**Available Fields:**
- `paperId`: Unique paper identifier
- `title`: Paper title
- `abstract`: Paper abstract
- `authors`: Array of author objects with names
- `venue`: Publication venue (journal/conference)
- `year`: Publication year
- `citationCount`: Number of citations
- `referenceCount`: Number of references
- `url`: Semantic Scholar URL
- `fieldsOfStudy`: Array of research fields
- `publicationTypes`: Array of publication types
- `openAccessPdf`: Open access PDF URL (if available)

**Search Syntax:**
- Plain text search: `"pancreaticobiliary stent"` (space-separated terms)
- Multi-word phrases: `"stent deployment mechanism"` (all terms searched together)
- Single keywords: `"polyethylene"` or `"biliary"`
- Technical terms: `"threaded stent"` or `"spiral deployment"`
- **Note**: No special operators (AND, OR, NOT, wildcards) are supported - use plain text only
- **Important**: Avoid hyphens in queries (use "machine learning" not "machine-learning")

**Response Format:**
```json
{
  "total": 1234,
  "offset": 0,
  "next": 30,
  "data": [
    {
      "paperId": "abc123",
      "title": "Paper Title",
      "abstract": "Paper abstract text...",
      "authors": [
        {
          "authorId": "123",
          "name": "John Doe"
        }
      ],
      "venue": "Journal Name",
      "year": 2023,
      "citationCount": 45,
      "url": "https://www.semanticscholar.org/paper/abc123",
      "fieldsOfStudy": ["Computer Science", "Medicine"],
      "publicationTypes": ["JournalArticle"],
      "openAccessPdf": {
        "url": "https://arxiv.org/pdf/2301.12345.pdf"
      }
    }
  ]
}
```

## Response Format

Both APIs return JSON responses with the following general structure:

**Success Response:**
```json
{
  "success": true,
  "data": [...],
  "total_hits": 123
}
```

**Error Response:**
```json
{
  "success": false,
  "error": "Error message",
  "details": "Additional error details"
}
```

## Rate Limiting

- **PatentView**: No explicit rate limits documented, but the system implements 1-second delays between requests
- **Semantic Scholar**: Rate limited to 1 request per second (enforced by the system with 1.5-second delays)

## Error Handling

The system implements automatic retry logic for:
- Network timeouts
- Rate limit errors (429)
- Server errors (500, 502, 503)

Maximum 3 retries with exponential backoff.

## Usage in the System

### Patent Search Agent
1. Reads keywords from DynamoDB
2. Constructs PatentView queries for each keyword
3. Executes searches via MCP Gateway
4. Deduplicates and pre-filters results
5. Uses LLM to evaluate relevance
6. Stores top results in DynamoDB

### Scholarly Article Agent
1. Reads invention context from DynamoDB
2. Uses LLM to generate strategic search queries
3. Executes Semantic Scholar searches via MCP Gateway
4. Applies adaptive query refinement
5. Uses LLM to evaluate semantic relevance
6. Stores top results in DynamoDB

## API Gateway Configuration

Both APIs are accessed through AWS Bedrock MCP Gateways, which provide:
- OAuth 2.0 authentication management
- Request/response transformation
- Rate limiting and throttling
- Monitoring and logging
- Secure credential storage

Gateway configuration is managed in the AWS Console under Bedrock → Model Context Protocol.

## Additional Resources

- **[PatentView API Documentation](https://search.patentsview.org/docs/docs/Search%20API/SearchAPIReference/?_gl=1*1vpmvct*_ga*MTEwOTIwMTMwLjE3NTg1NzA1NjM.*_ga_K4PTTLH074*czE3NjIxOTE3NDkkbzEzJGcwJHQxNzYyMTkxNzQ5JGo2MCRsMCRoMA..)** - Search API Reference
- **[Semantic Scholar API Documentation](https://api.semanticscholar.org/api-docs/)** - Academic Paper Search API
- **[AWS Bedrock MCP Documentation](https://docs.aws.amazon.com/bedrock/latest/userguide/model-context-protocol.html)** - Model Context Protocol Guide
