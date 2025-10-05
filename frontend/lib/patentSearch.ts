import { BedrockAgentCoreClient, InvokeAgentRuntimeCommand } from "@aws-sdk/client-bedrock-agentcore";
import { DynamoDBClient } from "@aws-sdk/client-dynamodb";
import { DynamoDBDocumentClient, QueryCommand } from "@aws-sdk/lib-dynamodb";
import type { PatentSearchResult, PatentSearchResponse } from "@/types";


/**
 * Patent search service using Bedrock Agent Core
 */
export class PatentSearchService {
  private bedrockClient: BedrockAgentCoreClient;
  private docClient: DynamoDBDocumentClient;
  private agentRuntimeArn: string;
  private resultsTableName: string;

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
    
    if (!agentRuntimeArn) {
      throw new Error("NEXT_PUBLIC_BEDROCK_AGENT_RUNTIME_ARN environment variable is required");
    }
    if (!resultsTableName) {
      throw new Error("NEXT_PUBLIC_PATENT_SEARCH_RESULTS_TABLE environment variable is required");
    }
    
    this.agentRuntimeArn = agentRuntimeArn;
    this.resultsTableName = resultsTableName;
  }

  /**
   * Sleep utility function
   */
  private sleep(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  /**
   * Trigger patent search using Bedrock Agent Core
   */
  async triggerPatentSearch(pdfFilename: string): Promise<string> {
    if (!pdfFilename) {
      throw new Error("PDF filename is required");
    }

    const cleanFilename = this.cleanFilename(pdfFilename);
    
    const payload = {
      action: "search_patents",
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
    
    const textResponse = await response.response.transformToString();
    
    // Return a search ID or session ID for tracking
    return input.runtimeSessionId;
  }

  /**
   * Fetch patent search results from DynamoDB
   */
  async fetchSearchResults(pdfFilename: string): Promise<PatentSearchResult[]> {
    if (!pdfFilename) {
      throw new Error("PDF filename is required");
    }

    const cleanFilename = this.cleanFilename(pdfFilename);

    const params = new QueryCommand({
      TableName: this.resultsTableName,
      KeyConditionExpression: "pdf_filename = :filename",
      ExpressionAttributeValues: {
        ":filename": cleanFilename,
      },
      ScanIndexForward: false, // Get most recent first
    });

    const result = await this.docClient.send(params);
    
    if (!result.Items || result.Items.length === 0) {
      return [];
    }
    return result.Items as PatentSearchResult[];
  }

  /**
   * Poll for search results until they're available
   */
  async pollForSearchResults(
    pdfFilename: string,
    maxAttempts: number = 20, // Reduced since we wait 3 minutes first
    delayMs: number = 30000 // 30 seconds between polls
  ): Promise<PatentSearchResult[]> {
    for (let attempt = 0; attempt < maxAttempts; attempt++) {
      try {
        const results = await this.fetchSearchResults(pdfFilename);

        if (results.length > 0) {
          return results;
        }

        // Wait 30 seconds before next attempt
        await this.sleep(delayMs);
      } catch (error) {
        console.error("Error polling for search results:", error);
        // Wait 30 seconds before retrying
        await this.sleep(delayMs);
      }
    }

    return []; // Timeout
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
export const patentSearchService = new PatentSearchService();
