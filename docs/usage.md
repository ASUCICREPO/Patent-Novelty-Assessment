# Patent Novelty Assessment System - Backend Testing Guide

This guide provides step-by-step instructions for testing the deployed Patent Novelty Assessment System directly from the AWS Console, without using the frontend application.

**Prerequisites:**
- Deployment completed successfully (all 4 phases from deployment guide)
- Agent Runtime showing "Healthy" status
- Lambda functions updated with Agent Runtime ARN

---

## Testing Overview

You can test the system in two ways:

1. **Automated Flow:** Upload PDF to S3 → Automatic agent triggering
2. **Manual Agent Testing:** Test each agent individually via Agent Core Console

---

## Method 1: Automated Flow Testing (End-to-End)

This tests the complete workflow as it would run in production.

### Step 1: Upload Test PDF to S3

1. Go to **AWS S3 Console**
2. Navigate to your bucket: `patent-novelty-pdf-processing-<account-id>`
3. Open the `uploads/` folder
4. Click **Upload**
5. Select a test PDF (invention disclosure document)
   - Must be a text-based PDF (not scanned images)
   - Should contain technical description of an invention
6. Click **Upload**

**What happens automatically:**
- S3 event triggers `pdf_processor` Lambda
- Lambda invokes BDA to extract text
- BDA stores results in `temp/docParser/` folder
- S3 event triggers `agent_trigger` Lambda
- Lambda invokes Keyword Generator Agent
- Lambda invokes Commercial Assessment Agent

### Step 2: Monitor BDA Processing

1. Go to **AWS S3 Console** → Your bucket
2. Navigate to `temp/docParser/`
3. You should see a folder named: `<filename>-<timestamp>/`
4. Inside, look for: `<job-id>/0/standard_output/0/result.json`
5. This file contains the extracted text from your PDF

**Expected time:** 30-60 seconds

### Step 3: Check Keyword Extraction Results

1. Go to **AWS DynamoDB Console**
2. Select table: `patent-keywords-<account-id>`
3. Click **Explore table items**
4. Look for an item with `pdf_filename` matching your uploaded file
5. Verify fields:
   - `title`: Invention title
   - `technology_description`: Technical description
   - `technology_applications`: Applications
   - `keywords`: Comma-separated keywords (12-15 keywords)
   - `processing_status`: Should be "completed"

**Expected time:** 1-2 minutes after BDA completes

### Step 4: Check Commercial Assessment Results

1. Go to **AWS DynamoDB Console**
2. Select table: `early-commercial-assessment-<account-id>`
3. Click **Explore table items**
4. Look for an item with `pdf_filename` matching your uploaded file
5. Verify fields include:
   - `problem_solved`
   - `solution_offered`
   - `non_confidential_abstract`
   - `technology_details`
   - `market_overview`
   - And 6 other assessment fields

**Expected time:** 2-3 minutes after BDA completes

### Step 5: Check CloudWatch Logs

If something doesn't work, check the logs:

1. Go to **AWS CloudWatch Console** → **Log groups**
2. Check these log groups:
   - `/aws/lambda/<PdfProcessorFunctionName>` - BDA invocation logs
   - `/aws/lambda/<AgentTriggerFunctionName>` - Agent triggering logs
   - `/aws/bedrock-agentcore/<agent-runtime-id>` - Agent execution logs

**Look for:**
- ✅ "Successfully initiated BDA processing"
- ✅ "Keyword Generator invoked successfully"
- ✅ "Commercial Assessment invoked successfully"
- ❌ Any error messages or stack traces

---

## Method 2: Manual Agent Testing (Individual Agents)

Test each agent individually to verify functionality.

### Prerequisites for Manual Testing

You need:
- A PDF file already processed by BDA (complete Method 1 Step 1-2 first)
- The `pdf_filename` (without .pdf extension)
- The BDA result file path: `temp/docParser/<filename-timestamp>/<job-id>/0/standard_output/0/result.json`

### Test 1: Keyword Generator Agent

1. Go to **AWS Bedrock Console** → **Agent Core** → **Agent runtime**
2. Select your `Patent-Novelty-Agent`
3. Click **Test in console**
4. In the test interface, enter this payload:

```json
{
  "action": "generate_keywords",
  "pdf_filename": "your-filename-without-extension",
  "bda_file_path": "temp/docParser/your-filename-timestamp/job-id/0/standard_output/0/result.json",
  "prompt": "Conduct a professional patent search keyword analysis for the invention disclosure document"
}
```

**Replace:**
- `your-filename-without-extension` with your actual filename (e.g., "ROI2022-013-test01")
- `bda_file_path` with the actual path from S3

**Expected Response:**
- Agent will read the BDA results
- Extract keywords, title, description, applications
- Store in DynamoDB
- Return success message

**Verify Results:**
- Check `patent-keywords-<account-id>` DynamoDB table
- Should see new item with your `pdf_filename`

### Test 2: Patent Search Agent

**Prerequisites:** Keywords must be generated first (Test 1 completed)

1. In the Agent Core test console, enter this payload:

```json
{
  "action": "search_patents",
  "pdf_filename": "your-filename-without-extension"
}
```

**Expected Response:**
- Agent reads keywords from DynamoDB
- Searches PatentView for each keyword
- Evaluates relevance using LLM
- Stores top 8 patents in DynamoDB
- Returns summary of search results

**Verify Results:**
- Check `patent-search-results-<account-id>` DynamoDB table
- Should see 8 items with your `pdf_filename`
- Each item has `relevance_score` and `llm_examiner_notes`

**Expected time:** 12-15 minutes (searches and evaluates ~30 patents)

### Test 3: Scholarly Article Search Agent

**Prerequisites:** Keywords must be generated first (Test 1 completed)

1. In the Agent Core test console, enter this payload:

```json
{
  "action": "search_articles",
  "pdf_filename": "your-filename-without-extension"
}
```

**Expected Response:**
- Agent reads keywords from DynamoDB
- Generates strategic search queries using LLM
- Searches Semantic Scholar
- Evaluates relevance using LLM
- Stores top 8 papers in DynamoDB
- Returns summary of search results

**Verify Results:**
- Check `scholarly-articles-results-<account-id>` DynamoDB table
- Should see 8 items with your `pdf_filename`
- Each item has `relevance_score` and `novelty_impact_assessment`

**Expected time:** 10-15 minutes (searches and evaluates ~30 papers)

### Test 4: Commercial Assessment Agent

**Prerequisites:** BDA processing completed (Method 1 Step 1-2)

1. In the Agent Core test console, enter this payload:

```json
{
  "action": "commercial_assessment",
  "pdf_filename": "your-filename-without-extension",
  "bda_file_path": "temp/docParser/your-filename-timestamp/job-id/0/standard_output/0/result.json"
}
```

**Expected Response:**
- Agent reads BDA results
- Analyzes 10 commercialization dimensions
- Stores assessment in DynamoDB
- Returns success message

**Verify Results:**
- Check `early-commercial-assessment-<account-id>` DynamoDB table
- Should see item with all 10 assessment fields

**Expected time:** 2-3 minutes

### Test 5: Report Generator

**Prerequisites:** 
- Keywords generated (Test 1)
- Patents searched (Test 2)
- Articles searched (Test 3)
- Commercial assessment completed (Test 4)

1. In the Agent Core test console, enter this payload:

```json
{
  "action": "generate_report",
  "pdf_filename": "your-filename-without-extension"
}
```

**Expected Response:**
- Agent reads data from all DynamoDB tables
- Generates 2 PDF reports using ReportLab
- Uploads to S3 `reports/` folder
- Returns S3 paths for both reports

**Verify Results:**
- Go to **AWS S3 Console** → Your bucket → `reports/` folder
- Should see 2 files:
  - `<filename>_report.pdf` (Novelty Report)
  - `<filename>_eca_report.pdf` (ECA Report)
- Download and verify PDF contents

**Expected time:** 3-5 seconds

---

## Monitoring and Debugging

### CloudWatch Logs Structure

**Lambda Logs:**
- `/aws/lambda/<PdfProcessorFunctionName>` - PDF upload and BDA invocation
- `/aws/lambda/<AgentTriggerFunctionName>` - Automatic agent triggering
- `/aws/lambda/<S3ApiFunctionName>` - S3 API operations (if using frontend)
- `/aws/lambda/<DynamoDBApiFunctionName>` - DynamoDB API operations
- `/aws/lambda/<AgentInvokeApiFunctionName>` - Manual agent invocations

**Agent Core Logs:**
- `/aws/bedrock-agentcore/<agent-runtime-id>` - All agent executions
  - Look for: Tool calls, LLM responses, errors
  - Filter by `pdf_filename` to find specific executions

### Common Issues and Solutions

#### Issue: Keywords Not Generated

**Check:**
1. BDA processing completed? (Check `temp/docParser/` in S3)
2. Agent trigger Lambda invoked? (Check CloudWatch logs)
3. Agent Runtime healthy? (Check Agent Core console)
4. Environment variables set? (Check Agent Runtime configuration)

**Solution:**
- Review CloudWatch logs for error messages
- Verify all 14 environment variables are set correctly
- Check IAM role has correct permissions

#### Issue: Patent/Article Search Fails

**Check:**
1. Keywords exist in DynamoDB? (Check `patent-keywords` table)
2. Gateway credentials correct? (Check environment variables)
3. OAuth tokens working? (Check CloudWatch logs for 401/403 errors)

**Solution:**
- Verify gateway credentials (8 variables) are correct
- Test gateway connectivity manually
- Check if API keys are valid

#### Issue: Report Generation Fails

**Check:**
1. All data exists in DynamoDB? (Keywords, patents, articles)
2. S3 bucket permissions correct? (Agent role has PutObject permission)

**Solution:**
- Verify data exists in all required tables
- Check CloudWatch logs for specific error
- Ensure at least some patents/articles are marked `add_to_report: Yes`

---

## Next Steps

After successful backend testing:

1. **Test Frontend Application:**
   - Navigate to Frontend URL
   - Test file upload via UI
   - Verify results display correctly

2. **Configure API Keys (Optional):**
   - Get PatentView API key for higher rate limits
   - Get Semantic Scholar API key for higher rate limits
   - Update identities in Agent Core console

3. **Set Up Monitoring:**
   - Create CloudWatch alarms for Lambda errors
   - Set up SNS notifications for failures
   - Monitor DynamoDB capacity metrics

4. **Production Readiness:**
   - Test with multiple PDFs
   - Verify concurrent processing works
   - Test error handling and recovery
   - Document any custom configurations

---

## Support

If you encounter issues during testing:

1. Check CloudWatch Logs for detailed error messages
2. Verify all environment variables are set correctly
3. Ensure IAM roles have correct permissions
4. Review the [Deployment Guide](./deploymentGuide.md) for configuration steps
5. Check the [Architecture Deep Dive](./architectureDeepDive.md) for system details

---

**Testing Complete!** Your Patent Novelty Assessment System is verified and ready for production use.
