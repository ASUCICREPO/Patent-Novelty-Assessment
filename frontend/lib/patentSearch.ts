import { BedrockAgentCoreClient, InvokeAgentRuntimeCommand } from "@aws-sdk/client-bedrock-agentcore";
import AWS from "aws-sdk";
import type { PatentSearchResult, PatentSearchResponse } from "@/types";

/**
 * Patent search service using Bedrock Agent Core
 */
export class PatentSearchService {
  private bedrockClient: BedrockAgentCoreClient;
  private dynamodb: AWS.DynamoDB.DocumentClient;
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

    // Initialize DynamoDB client
    this.dynamodb = new AWS.DynamoDB.DocumentClient({
      accessKeyId: process.env.NEXT_PUBLIC_AWS_ACCESS_KEY_ID,
      secretAccessKey: process.env.NEXT_PUBLIC_AWS_SECRET_ACCESS_KEY,
      region: process.env.NEXT_PUBLIC_AWS_REGION || "us-west-2",
    });

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
   * Trigger patent search using Bedrock Agent Core
   */
  async triggerPatentSearch(pdfFilename: string): Promise<string> {
    try {
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
    } catch (error) {
      console.error("Error triggering patent search:", error);
      
      // Provide more specific error messages
      if (error instanceof Error) {
        if (error.message.includes("credentials")) {
          throw new Error("AWS credentials are invalid or missing. Please check your environment variables.");
        } else if (error.message.includes("region")) {
          throw new Error("Invalid AWS region. Please check your region configuration.");
        } else if (error.message.includes("agent")) {
          throw new Error("Bedrock Agent Core runtime not found. Please verify the agent ARN.");
        }
      }
      
      throw new Error(`Failed to trigger patent search: ${error instanceof Error ? error.message : 'Unknown error'}`);
    }
  }

  /**
   * Fetch patent search results from DynamoDB
   */
  async fetchSearchResults(pdfFilename: string): Promise<PatentSearchResult[]> {
    try {
      if (!pdfFilename) {
        throw new Error("PDF filename is required");
      }

      const cleanFilename = this.cleanFilename(pdfFilename);

      const params = {
        TableName: this.resultsTableName,
        KeyConditionExpression: "pdf_filename = :filename",
        ExpressionAttributeValues: {
          ":filename": cleanFilename,
        },
        ScanIndexForward: false, // Get most recent first
      };

      const result = await this.dynamodb.query(params).promise();
      
      if (!result.Items || result.Items.length === 0) {
        return [];
      }

      return result.Items as PatentSearchResult[];
    } catch (error) {
      console.error("Error fetching search results:", error);
      
      // Provide more specific error messages
      if (error instanceof Error) {
        if (error.message.includes("credentials")) {
          throw new Error("AWS credentials are invalid or missing. Please check your environment variables.");
        } else if (error.message.includes("region")) {
          throw new Error("Invalid AWS region. Please check your region configuration.");
        } else if (error.message.includes("table")) {
          throw new Error("DynamoDB table not found. Please verify the table name configuration.");
        }
      }
      
      throw new Error(`Failed to fetch search results: ${error instanceof Error ? error.message : 'Unknown error'}`);
    }
  }

  /**
   * Poll for search results until they're available
   */
  async pollForSearchResults(
    pdfFilename: string,
    maxAttempts: number = 30,
    delayMs: number = 5000
  ): Promise<PatentSearchResult[]> {
    for (let attempt = 0; attempt < maxAttempts; attempt++) {
      const results = await this.fetchSearchResults(pdfFilename);

      if (results.length > 0) {
        return results;
      }

      // Wait before next attempt
      await new Promise((resolve) => setTimeout(resolve, delayMs));
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
