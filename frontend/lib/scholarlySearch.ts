import { BedrockAgentCoreClient, InvokeAgentRuntimeCommand } from "@aws-sdk/client-bedrock-agentcore";
import { DynamoDBClient } from "@aws-sdk/client-dynamodb";
import { DynamoDBDocumentClient, QueryCommand, UpdateCommand } from "@aws-sdk/lib-dynamodb";
import type { ScholarlyArticle } from "@/types";

// Configure DynamoDB v3
const ddbClient = new DynamoDBClient({
  region: process.env.NEXT_PUBLIC_AWS_REGION || "us-west-2",
  credentials: {
    accessKeyId: process.env.NEXT_PUBLIC_AWS_ACCESS_KEY_ID || "",
    secretAccessKey: process.env.NEXT_PUBLIC_AWS_SECRET_ACCESS_KEY || "",
  },
});
const docClient = DynamoDBDocumentClient.from(ddbClient);
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
      
      // Response received successfully
      await response.response.transformToString();
      
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
      
      const params = new QueryCommand({
        TableName: this.resultsTableName,
        KeyConditionExpression: "pdf_filename = :filename",
        ExpressionAttributeValues: {
          ":filename": cleanFilename,
        },
        ScanIndexForward: false, // Get most recent first
      });

      const result = await docClient.send(params);
      
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
   * Check if filename count has reached the expected number (8) before polling
   */
  async checkFilenameCount(pdfFilename: string, expectedCount: number = 8): Promise<boolean> {
    try {
      const cleanFilename = this.cleanFilename(pdfFilename);
      
      const params = new QueryCommand({
        TableName: this.resultsTableName,
        KeyConditionExpression: "pdf_filename = :filename",
        ExpressionAttributeValues: {
          ":filename": cleanFilename,
        },
        Select: "COUNT", // Only get count, not full items
      });

      const result = await docClient.send(params);
      const count = result.Count || 0;
      
      console.log(`Filename count for ${cleanFilename}: ${count}/${expectedCount}`);
      return count >= expectedCount;
    } catch (error) {
      console.error("Error checking filename count:", error);
      return false;
    }
  }

  /**
   * Poll for scholarly article search results until they're available
   * Continues polling until filename count reaches expected number, then fetches results
   */
  async pollForSearchResults(
    pdfFilename: string,
    delayMs: number = 30000, // 30 seconds between polls
    expectedFilenameCount: number = 8
  ): Promise<ScholarlyArticle[]> {
    // Poll until filename count reaches expected number
    console.log(`Waiting for filename count to reach ${expectedFilenameCount}...`);
    while (true) {
      try {
        const countReached = await this.checkFilenameCount(pdfFilename, expectedFilenameCount);
        
        if (countReached) {
          console.log(`Filename count reached ${expectedFilenameCount}, fetching results...`);
          break;
        }
        
        console.log(`Count not yet reached, waiting ${delayMs/1000} seconds...`);
        
        // Wait before next count check
        await this.sleep(delayMs);
      } catch (error) {
        console.error("Error during count check:", error);
        await this.sleep(delayMs);
      }
    }
    
    // Fetch actual results once count is reached
    console.log("Fetching search results...");
    try {
      const results = await this.fetchSearchResults(pdfFilename);
      console.log(`Found ${results.length} search results`);
      return results;
    } catch (error) {
      console.error("Error fetching search results:", error);
      return [];
    }
  }

  /**
   * Update add_to_report field for a scholarly article
   */
  async updateAddToReport(pdfFilename: string, articleDoi: string, addToReport: boolean): Promise<void> {
    try {
      const cleanFilename = this.cleanFilename(pdfFilename);
      
      const params = new UpdateCommand({
        TableName: this.resultsTableName,
        Key: {
          pdf_filename: cleanFilename,
          article_doi: articleDoi,
        },
        UpdateExpression: "SET add_to_report = :addToReport",
        ExpressionAttributeValues: {
          ":addToReport": addToReport ? "Yes" : "No",
        },
        ReturnValues: "UPDATED_NEW",
      });

      await docClient.send(params);
      console.log(`Updated add_to_report for article ${articleDoi} to ${addToReport ? "Yes" : "No"}`);
    } catch (error) {
      console.error("Error updating add_to_report:", error);
      throw error;
    }
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
