import { BedrockAgentCoreClient, InvokeAgentRuntimeCommand } from "@aws-sdk/client-bedrock-agentcore";
import { DynamoDBClient } from "@aws-sdk/client-dynamodb";
import { DynamoDBDocumentClient } from "@aws-sdk/lib-dynamodb";

/**
 * Report generation service using Bedrock Agent Core
 */
export class ReportGenerationService {
  private bedrockClient: BedrockAgentCoreClient;
  private docClient: DynamoDBDocumentClient;
  private agentRuntimeArn: string;
  private resultsTableName: string;
  private s3BucketName: string;

  constructor() {
    // Validate required environment variables
    if (!process.env.NEXT_PUBLIC_AWS_ACCESS_KEY_ID || !process.env.NEXT_PUBLIC_AWS_SECRET_ACCESS_KEY) {
      console.warn("AWS credentials not found in environment variables");
    }

    // Initialize Bedrock Agent Core client
    this.bedrockClient = new BedrockAgentCoreClient({
      region: process.env.NEXT_PUBLIC_AWS_REGION || "us-west-2",
      credentials: {
        accessKeyId: process.env.NEXT_PUBLIC_AWS_ACCESS_KEY_ID || "",
        secretAccessKey: process.env.NEXT_PUBLIC_AWS_SECRET_ACCESS_KEY || "",
      },
    });

    // Initialize DynamoDB v3 Document client
    const ddbClient = new DynamoDBClient({
      region: process.env.NEXT_PUBLIC_AWS_REGION || "us-west-2",
      credentials: {
        accessKeyId: process.env.NEXT_PUBLIC_AWS_ACCESS_KEY_ID || "",
        secretAccessKey: process.env.NEXT_PUBLIC_AWS_SECRET_ACCESS_KEY || "",
      },
    });
    this.docClient = DynamoDBDocumentClient.from(ddbClient);


    // Validate and assign environment variables
    const agentRuntimeArn = process.env.NEXT_PUBLIC_BEDROCK_AGENT_RUNTIME_ARN;
    const resultsTableName = process.env.NEXT_PUBLIC_PATENT_SEARCH_RESULTS_TABLE;
    const s3BucketName = process.env.NEXT_PUBLIC_S3_BUCKET;
    
    if (!agentRuntimeArn) {
      throw new Error("NEXT_PUBLIC_BEDROCK_AGENT_RUNTIME_ARN environment variable is required");
    }
    if (!resultsTableName) {
      throw new Error("NEXT_PUBLIC_PATENT_SEARCH_RESULTS_TABLE environment variable is required");
    }
    if (!s3BucketName) {
      throw new Error("NEXT_PUBLIC_S3_BUCKET environment variable is required");
    }
    
    this.agentRuntimeArn = agentRuntimeArn;
    this.resultsTableName = resultsTableName;
    this.s3BucketName = s3BucketName;
  }

  /**
   * Trigger report generation using Bedrock Agent Core
   */
  async triggerReportGeneration(pdfFilename: string): Promise<string> {
    if (!pdfFilename) {
      throw new Error("PDF filename is required");
    }

    const cleanFilename = this.cleanFilename(pdfFilename);
    
    const payload = {
      action: "generate_report",
      pdf_filename: cleanFilename,
    };

    const input = {
      runtimeSessionId: this.generateSessionId(),
      agentRuntimeArn: this.agentRuntimeArn,
      qualifier: "DEFAULT",
      payload: new Uint8Array(Buffer.from(JSON.stringify(payload))),
    };

    const command = new InvokeAgentRuntimeCommand(input);
    const response = await this.bedrockClient.send(command);
    
    // Convert response to string
    if (!response.response) {
      throw new Error("No response received from Bedrock Agent Core");
    }
    
    // Response received successfully
    await response.response.transformToString();
    
    // Return a search ID or session ID for tracking
    return input.runtimeSessionId;
  }

  /**
   * Check if reports are ready using backend API (since S3 is not publicly accessible)
   */
  async checkReportsReady(pdfFilename: string): Promise<{ ptlsReady: boolean; ecaReady: boolean }> {
    try {
      const cleanFilename = this.cleanFilename(pdfFilename);
      
      console.log(`Checking reports via API for: ${cleanFilename}`);
      
      // Use backend API to check file existence
      const response = await fetch(`/api/check-reports?filename=${encodeURIComponent(cleanFilename)}`);
      
      if (!response.ok) {
        throw new Error(`API request failed: ${response.status} ${response.statusText}`);
      }
      
      const result = await response.json();
      console.log(`Report status for ${cleanFilename}: PTLS=${result.ptlsReady}, ECA=${result.ecaReady}`);
      
      return {
        ptlsReady: result.ptlsReady,
        ecaReady: result.ecaReady
      };
    } catch (error) {
      console.error("Error checking reports:", error);
      return {
        ptlsReady: false,
        ecaReady: false
      };
    }
  }


  /**
   * Get download URLs for the generated reports
   * Since files are not publicly accessible, we'll use the API to get signed URLs
   */
  async getReportDownloadUrls(pdfFilename: string): Promise<{ ptlsUrl: string; ecaUrl: string }> {
    try {
      const cleanFilename = this.cleanFilename(pdfFilename);
      
      // Use API to get signed URLs
      const response = await fetch(`/api/get-signed-urls?filename=${encodeURIComponent(cleanFilename)}`);
      
      if (!response.ok) {
        throw new Error(`Failed to get signed URLs: ${response.status}`);
      }
      
      const result = await response.json();
      return {
        ptlsUrl: result.ptlsUrl,
        ecaUrl: result.ecaUrl
      };
    } catch (error) {
      console.error("Error getting download URLs:", error);
      // Fallback to direct URLs (will show AccessDenied but at least won't crash)
      const region = process.env.NEXT_PUBLIC_AWS_REGION || "us-west-2";
      const baseUrl = `https://${this.s3BucketName}.s3.${region}.amazonaws.com`;
      return {
        ptlsUrl: `${baseUrl}/reports/${this.cleanFilename(pdfFilename)}_report.pdf`,
        ecaUrl: `${baseUrl}/reports/${this.cleanFilename(pdfFilename)}_eca_report.pdf`
      };
    }
  }

  /**
   * Clean filename by removing PDF extension
   */
  private cleanFilename(filename: string): string {
    return filename.replace(/\.pdf$/i, "");
  }

  /**
   * Generate a unique session ID for Bedrock Agent Core
   */
  private generateSessionId(): string {
    const chars = "abcdefghijklmnopqrstuvwxyz0123456789";
    let result = "";
    for (let i = 0; i < 33; i++) {
      result += chars.charAt(Math.floor(Math.random() * chars.length));
    }
    return result;
  }
}

// Export a singleton instance
export const reportGenerationService = new ReportGenerationService();
