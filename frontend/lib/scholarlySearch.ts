import AWS from "aws-sdk";
import { BedrockAgentCoreClient, InvokeAgentRuntimeCommand } from "@aws-sdk/client-bedrock-agentcore";
import type { ScholarlyArticle } from "@/types";

// Configure AWS
AWS.config.update({
  region: process.env.NEXT_PUBLIC_AWS_REGION || "us-west-2",
  accessKeyId: process.env.NEXT_PUBLIC_AWS_ACCESS_KEY_ID,
  secretAccessKey: process.env.NEXT_PUBLIC_AWS_SECRET_ACCESS_KEY,
});

const dynamodb = new AWS.DynamoDB.DocumentClient();
const bedrockClient = new BedrockAgentCoreClient({
  region: process.env.NEXT_PUBLIC_AWS_REGION || "us-west-2",
  credentials: {
    accessKeyId: process.env.NEXT_PUBLIC_AWS_ACCESS_KEY_ID!,
    secretAccessKey: process.env.NEXT_PUBLIC_AWS_SECRET_ACCESS_KEY!,
  },
});

export class ScholarlySearchService {
  private resultsTableName: string;
  private agentRuntimeArn: string;

  constructor() {
    this.resultsTableName = process.env.NEXT_PUBLIC_SCHOLARLY_RESULTS_TABLE_NAME!;
    this.agentRuntimeArn = process.env.NEXT_PUBLIC_BEDROCK_AGENT_RUNTIME_ARN!;
    
    if (!this.resultsTableName) {
      throw new Error("NEXT_PUBLIC_SCHOLARLY_RESULTS_TABLE_NAME environment variable is required");
    }
    
    if (!this.agentRuntimeArn) {
      throw new Error("NEXT_PUBLIC_BEDROCK_AGENT_RUNTIME_ARN environment variable is required");
    }
  }

  /**
   * Generate a unique session ID
   */
  private generateSessionId(): string {
    return `scholarly-search-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
  }

  /**
   * Trigger scholarly article search via Agent Core
   */
  async triggerScholarlySearch(pdfFilename: string): Promise<string> {
    if (!pdfFilename) {
      throw new Error("PDF filename is required");
    }

    const cleanFilename = this.cleanFilename(pdfFilename);
    
    try {
      const payload = {
        action: "search_articles",
        pdf_filename: cleanFilename,
      };

      const input = {
        runtimeSessionId: this.generateSessionId(),
        agentRuntimeArn: this.agentRuntimeArn,
        qualifier: "DEFAULT",
        payload: new Uint8Array(Buffer.from(JSON.stringify(payload))),
      };

      const command = new InvokeAgentRuntimeCommand(input);
      const response = await bedrockClient.send(command);
      
      // Convert response to string
      if (!response.response) {
        throw new Error("No response received from Bedrock Agent Core");
      }
      
      const textResponse = await response.response.transformToString();
      
      // Return a search ID or session ID for tracking
      return input.runtimeSessionId;
    } catch (error) {
      console.error("Error triggering scholarly search:", error);
      throw error;
    }
  }

  /**
   * Fetch scholarly article search results from DynamoDB
   */
  async fetchSearchResults(pdfFilename: string): Promise<ScholarlyArticle[]> {
    try {
      const cleanFilename = this.cleanFilename(pdfFilename);
      
      const params = {
        TableName: this.resultsTableName,
        KeyConditionExpression: "pdf_filename = :filename",
        ExpressionAttributeValues: {
          ":filename": cleanFilename,
        },
        ScanIndexForward: false, // Get most recent first
      };

      const result = await dynamodb.query(params).promise();
      
      if (!result.Items || result.Items.length === 0) {
        return [];
      }

      return result.Items as ScholarlyArticle[];
    } catch (error) {
      console.error("Error fetching scholarly search results:", error);
      throw error;
    }
  }

  /**
   * Poll for scholarly article search results until they're available
   */
  async pollForSearchResults(
    pdfFilename: string,
    maxAttempts: number = 30,
    delayMs: number = 5000
  ): Promise<ScholarlyArticle[]> {
    for (let attempt = 0; attempt < maxAttempts; attempt++) {
      try {
        const results = await this.fetchSearchResults(pdfFilename);

        if (results.length > 0) {
          return results;
        }

        // Wait before next attempt with exponential backoff for polling
        const pollDelay = Math.min(delayMs * Math.pow(1.1, attempt), 30000); // Max 30 seconds
        await this.sleep(pollDelay);
      } catch (error) {
        // For other errors, use normal delay
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
   * Sleep utility function
   */
  private sleep(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms));
  }
}

export const scholarlySearchService = new ScholarlySearchService();
