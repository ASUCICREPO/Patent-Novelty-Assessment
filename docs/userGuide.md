# User Guide

**Please ensure the application is deployed. Instructions in the deployment guide here:** [Deployment Guide](./deploymentGuide.md)

## Introduction

The Patent Novelty Assessment System automates the prior art search process for invention disclosures. Simply upload your invention disclosure PDF, and the system will automatically extract keywords, search patent databases and academic literature, evaluate relevance using AI, and generate professional PDF reports for patent examiners and technology transfer professionals.

The entire workflow is automated - from document upload to report generation - requiring no manual intervention.

## Step-by-Step Usage Instructions

### 1. Prepare Your Invention Disclosure Document

Ensure your invention disclosure is in PDF format and contains:
- Clear description of the invention
- Technical details and mechanisms
- Potential applications
- Problem being solved

![Step 1 - Prepare Document](./media/step-1-prepare-document.png)
> **[PLACEHOLDER]** Please provide a screenshot showing an example invention disclosure PDF and save as `docs/media/step-1-prepare-document.png`

### 2. Upload PDF to S3

Upload your invention disclosure PDF to the S3 bucket's `uploads/` folder:

**Option A: Using AWS Console**
1. Go to AWS Console → S3
2. Navigate to your bucket: `patent-novelty-pdf-processing-ACCOUNT_ID`
3. Click on the `uploads/` folder
4. Click "Upload"
5. Select your PDF file
6. Click "Upload"

**Option B: Using AWS CLI**
```bash
aws s3 cp your-invention.pdf s3://patent-novelty-pdf-processing-ACCOUNT_ID/uploads/
```

![Step 2 - Upload to S3](./media/step-2-upload-s3.png)
> **[PLACEHOLDER]** Please provide a screenshot showing the S3 upload interface with a PDF being uploaded to the uploads/ folder and save as `docs/media/step-2-upload-s3.png`

### 3. Automatic Document Processing

Once uploaded, the system automatically:
- Triggers BDA (Bedrock Data Automation) to extract text from the PDF
- Processes the document and stores results in `temp/docParser/` folder
- This typically takes 2-5 minutes depending on document length

You can monitor progress in CloudWatch Logs:
```bash
aws logs tail /aws/lambda/PatentNoveltyStack-PdfProcessorFunction --follow
```

![Step 3 - BDA Processing](./media/step-3-bda-processing.png)
> **[PLACEHOLDER]** Please provide a screenshot showing CloudWatch Logs with BDA processing messages and save as `docs/media/step-3-bda-processing.png`

### 4. Automatic Keyword Extraction

When BDA completes, the system automatically triggers the Keyword Generator Agent:
- Analyzes the invention disclosure using Claude 3.7 Sonnet
- Extracts strategic search keywords (12-15 keywords)
- Generates invention title, technology description, and applications
- Stores results in DynamoDB `patent-keywords` table

This process takes 1-2 minutes.

![Step 4 - Keyword Extraction](./media/step-4-keyword-extraction.png)
> **[PLACEHOLDER]** Please provide a screenshot showing DynamoDB table with extracted keywords and save as `docs/media/step-4-keyword-extraction.png`

### 5. Automatic Commercial Assessment

Simultaneously, the Commercial Assessment Agent:
- Analyzes commercialization potential
- Evaluates market size and competition
- Identifies potential licensees
- Assesses key challenges and assumptions
- Stores results in DynamoDB `early-commercial-assessment` table

This process takes 2-3 minutes.

![Step 5 - Commercial Assessment](./media/step-5-commercial-assessment.png)
> **[PLACEHOLDER]** Please provide a screenshot showing DynamoDB table with commercial assessment data and save as `docs/media/step-5-commercial-assessment.png`

### 6. Initiate Patent Search

Manually trigger the Patent Search Agent (or automate via additional Lambda):

**Using AWS Console:**
1. Go to AWS Console → Bedrock → Agent Core
2. Select your Patent Novelty Orchestrator runtime
3. Click "Test" or "Invoke"
4. Enter payload:
```json
{
  "action": "search_patents",
  "pdf_filename": "your-invention"
}
```
5. Click "Invoke"

**Using AWS CLI:**
```bash
aws bedrock-agentcore invoke-agent-runtime \
  --agent-runtime-arn "arn:aws:bedrock-agentcore:REGION:ACCOUNT:runtime/RUNTIME-ID" \
  --runtime-session-id "session-$(date +%s)" \
  --payload '{"action":"search_patents","pdf_filename":"your-invention"}'
```

The Patent Search Agent will:
- Search PatentView for each keyword
- Deduplicate and pre-filter by citation count
- Use LLM to evaluate relevance of each patent
- Store top 6-8 most relevant patents in DynamoDB

This process takes 3-5 minutes.

![Step 6 - Patent Search](./media/step-6-patent-search.png)
> **[PLACEHOLDER]** Please provide a screenshot showing the Agent Core invocation interface with patent search action and save as `docs/media/step-6-patent-search.png`

### 7. Initiate Academic Literature Search

Trigger the Scholarly Article Search Agent:

**Payload:**
```json
{
  "action": "search_articles",
  "pdf_filename": "your-invention"
}
```

The Scholarly Article Agent will:
- Generate strategic search queries using LLM
- Search Semantic Scholar with adaptive refinement
- Apply LLM-powered semantic relevance filtering
- Store top 5-8 most relevant papers in DynamoDB

This process takes 4-6 minutes.

![Step 7 - Article Search](./media/step-7-article-search.png)
> **[PLACEHOLDER]** Please provide a screenshot showing the Agent Core invocation interface with article search action and save as `docs/media/step-7-article-search.png`

### 8. Mark Results for Report Inclusion

Review search results in DynamoDB and mark relevant items for report inclusion:

**For Patents:**
1. Go to DynamoDB → `patent-search-results` table
2. Find patents for your case (filter by `pdf_filename`)
3. For each relevant patent, edit the item and set:
   - `add_to_report` = `"Yes"`
4. Save changes

**For Articles:**
1. Go to DynamoDB → `scholarly-articles-results` table
2. Find articles for your case (filter by `pdf_filename`)
3. For each relevant article, edit the item and set:
   - `add_to_report` = `"Yes"`
4. Save changes

![Step 8 - Mark Results](./media/step-8-mark-results.png)
> **[PLACEHOLDER]** Please provide a screenshot showing DynamoDB item editor with add_to_report field being set to "Yes" and save as `docs/media/step-8-mark-results.png`

### 9. Generate PDF Reports

Trigger the Report Generator:

**Payload:**
```json
{
  "action": "generate_report",
  "pdf_filename": "your-invention"
}
```

The Report Generator will:
- Fetch all data from DynamoDB tables
- Generate two professional PDF reports:
  - **Novelty Report** - Patent and literature search results with abstracts
  - **ECA Report** - Early commercial assessment findings
- Upload reports to S3 `reports/` folder

This process takes 1-2 minutes.

![Step 9 - Generate Reports](./media/step-9-generate-reports.png)
> **[PLACEHOLDER]** Please provide a screenshot showing the Agent Core invocation interface with generate_report action and save as `docs/media/step-9-generate-reports.png`

### 10. Download and Review Reports

Download the generated PDF reports from S3:

**Using AWS Console:**
1. Go to AWS Console → S3
2. Navigate to your bucket: `patent-novelty-pdf-processing-ACCOUNT_ID`
3. Click on the `reports/` folder
4. Find your reports:
   - `your-invention_report.pdf` (Novelty Report)
   - `your-invention_eca_report.pdf` (ECA Report)
5. Click on each file and click "Download"

**Using AWS CLI:**
```bash
# Download Novelty Report
aws s3 cp s3://patent-novelty-pdf-processing-ACCOUNT_ID/reports/your-invention_report.pdf ./

# Download ECA Report
aws s3 cp s3://patent-novelty-pdf-processing-ACCOUNT_ID/reports/your-invention_eca_report.pdf ./
```

![Step 10 - Download Reports](./media/step-10-download-reports.png)
> **[PLACEHOLDER]** Please provide a screenshot showing the S3 interface with generated PDF reports in the reports/ folder and save as `docs/media/step-10-download-reports.png`

### 11. Review Generated Reports

Open the PDF reports to review:

**Novelty Report Contents:**
- Case information (filename, title, keywords)
- Patent search results table (patent number, inventors, assignees, title)
- Literature search results table (journal, year, authors, title)
- Detailed prior art analysis with abstracts for each patent and paper
- Legal disclaimer

**ECA Report Contents:**
- Case information
- Problem solved and solution offered
- Non-confidential marketing abstract
- Technology details
- Potential applications
- Market overview
- Competition analysis
- Potential licensees
- Key commercialization challenges
- Key assumptions
- Key companies
- Legal disclaimer

![Step 11 - Review Reports](./media/step-11-review-reports.png)
> **[PLACEHOLDER]** Please provide a screenshot showing an opened PDF report with visible content (novelty report or ECA report) and save as `docs/media/step-11-review-reports.png`

## Tips for Best Results

### Document Quality
- Ensure PDFs are text-based (not scanned images)
- Include clear technical descriptions
- Provide specific details about mechanisms and materials
- Describe the problem being solved

### Keyword Review
- Review extracted keywords in DynamoDB before running searches
- Manually edit keywords if needed for better search results
- Add domain-specific terminology if missing

### Result Selection
- Review LLM relevance scores in DynamoDB
- Mark only truly relevant patents/articles for report inclusion
- Aim for 6-8 patents and 5-8 articles per report
- Consider citation counts as an indicator of impact

### Report Customization
- Reports are AI-generated and require manual review
- Verify all prior art references are accurate
- Add additional analysis or commentary as needed
- Use reports as a starting point for examiner review

## Monitoring and Troubleshooting

### Check Processing Status

Monitor CloudWatch Logs for each component:

```bash
# PDF Processor
aws logs tail /aws/lambda/PatentNoveltyStack-PdfProcessorFunction --follow

# Agent Trigger
aws logs tail /aws/lambda/PatentNoveltyStack-AgentTriggerFunction --follow

# Agent Core Runtime
# View logs in AWS Console → Bedrock → Agent Core → Your Runtime → Logs
```

### Common Issues

**Issue: No keywords extracted**
- Check BDA processing completed successfully
- Verify PDF contains extractable text (not scanned image)
- Review CloudWatch Logs for errors

**Issue: No search results**
- Verify keywords are relevant and not too specific
- Check gateway credentials are configured correctly
- Review Agent Core Runtime logs for API errors

**Issue: Reports not generated**
- Ensure at least one patent or article is marked with `add_to_report = "Yes"`
- Verify all DynamoDB tables contain data
- Check S3 bucket permissions

**Issue: Low-quality results**
- Review and refine extracted keywords
- Adjust LLM relevance score thresholds in agent code
- Run additional searches with different keyword combinations

## Next Steps

After reviewing reports:
1. Share with patent examiners for novelty assessment
2. Use ECA report for commercialization decision-making
3. Conduct deeper analysis on identified prior art
4. Refine invention disclosure based on findings
5. Proceed with patent filing or licensing discussions
