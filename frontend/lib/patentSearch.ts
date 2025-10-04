import { BedrockAgentCoreClient, InvokeAgentRuntimeCommand } from "@aws-sdk/client-bedrock-agentcore";
import AWS from "aws-sdk";
import type { PatentSearchResult, PatentSearchResponse } from "@/types";

/**
 * Rate limiting configuration
 */
interface RateLimitConfig {
  maxRetries: number;
  baseDelayMs: number;
  maxDelayMs: number;
  backoffMultiplier: number;
  jitterMs: number;
}

/**
 * Request queue item
 */
interface QueuedRequest {
  id: string;
  resolve: (value: any) => void;
  reject: (error: any) => void;
  execute: () => Promise<any>;
  timestamp: number;
}

/**
 * Patent search service using Bedrock Agent Core
 */
export class PatentSearchService {
  private bedrockClient: BedrockAgentCoreClient;
  private dynamodb: AWS.DynamoDB.DocumentClient;
  private agentRuntimeArn: string;
  private resultsTableName: string;
  private requestQueue: QueuedRequest[] = [];
  private isProcessingQueue: boolean = false;
  private rateLimitConfig: RateLimitConfig;
  private lastRequestTime: number = 0;
  private minRequestInterval: number = 2000; // 2 seconds between requests

  constructor() {
    // Initialize rate limiting configuration
    this.rateLimitConfig = {
      maxRetries: 5,
      baseDelayMs: 1000,
      maxDelayMs: 30000,
      backoffMultiplier: 2,
      jitterMs: 500
    };

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
   * Execute a request with exponential backoff and retry logic
   */
  private async executeWithRetry<T>(
    operation: () => Promise<T>,
    operationName: string = "API call"
  ): Promise<T> {
    let lastError: Error | null = null;
    
    for (let attempt = 0; attempt <= this.rateLimitConfig.maxRetries; attempt++) {
      try {
        // Add jitter to prevent thundering herd
        if (attempt > 0) {
          const delay = this.calculateDelay(attempt);
          console.log(`${operationName} attempt ${attempt + 1}, waiting ${delay}ms...`);
          await this.sleep(delay);
        }

        return await operation();
      } catch (error) {
        lastError = error as Error;
        
        // Check if it's a rate limiting error
        if (this.isRateLimitError(error)) {
          console.warn(`${operationName} rate limited on attempt ${attempt + 1}`);
          
          if (attempt === this.rateLimitConfig.maxRetries) {
            throw new Error(`Rate limit exceeded after ${this.rateLimitConfig.maxRetries} retries. Please try again later.`);
          }
          continue;
        }
        
        // For non-rate-limit errors, throw immediately
        throw error;
      }
    }
    
    throw lastError || new Error(`${operationName} failed after ${this.rateLimitConfig.maxRetries} retries`);
  }

  /**
   * Check if an error is a rate limiting error
   */
  private isRateLimitError(error: any): boolean {
    if (!error) return false;
    
    const errorMessage = error.message || error.toString();
    const errorCode = error.code || error.$metadata?.httpStatusCode;
    
    return (
      errorCode === 429 ||
      errorMessage.includes("429") ||
      errorMessage.includes("Too Many Requests") ||
      errorMessage.includes("Rate exceeded") ||
      errorMessage.includes("throttled")
    );
  }

  /**
   * Calculate delay with exponential backoff and jitter
   */
  private calculateDelay(attempt: number): number {
    const exponentialDelay = Math.min(
      this.rateLimitConfig.baseDelayMs * Math.pow(this.rateLimitConfig.backoffMultiplier, attempt - 1),
      this.rateLimitConfig.maxDelayMs
    );
    
    const jitter = Math.random() * this.rateLimitConfig.jitterMs;
    return Math.floor(exponentialDelay + jitter);
  }

  /**
   * Sleep utility function
   */
  private sleep(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  /**
   * Add request to queue and process with throttling
   */
  private async queueRequest<T>(operation: () => Promise<T>): Promise<T> {
    return new Promise((resolve, reject) => {
      const requestId = this.generateSessionId();
      const queuedRequest: QueuedRequest = {
        id: requestId,
        resolve,
        reject,
        execute: operation,
        timestamp: Date.now()
      };

      this.requestQueue.push(queuedRequest);
      this.processQueue();
    });
  }

  /**
   * Process the request queue with throttling
   */
  private async processQueue(): Promise<void> {
    if (this.isProcessingQueue || this.requestQueue.length === 0) {
      return;
    }

    this.isProcessingQueue = true;

    while (this.requestQueue.length > 0) {
      const request = this.requestQueue.shift();
      if (!request) break;

      try {
        // Ensure minimum interval between requests
        const timeSinceLastRequest = Date.now() - this.lastRequestTime;
        if (timeSinceLastRequest < this.minRequestInterval) {
          const waitTime = this.minRequestInterval - timeSinceLastRequest;
          console.log(`Throttling request, waiting ${waitTime}ms...`);
          await this.sleep(waitTime);
        }

        const result = await request.execute();
        this.lastRequestTime = Date.now();
        request.resolve(result);
      } catch (error) {
        request.reject(error);
      }
    }

    this.isProcessingQueue = false;
  }

  /**
   * Trigger patent search using Bedrock Agent Core
   */
  async triggerPatentSearch(pdfFilename: string): Promise<string> {
    if (!pdfFilename) {
      throw new Error("PDF filename is required");
    }

    const cleanFilename = this.cleanFilename(pdfFilename);
    
    return this.queueRequest(async () => {
      return this.executeWithRetry(async () => {
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
      }, "Patent search trigger");
    });
  }

  /**
   * Fetch patent search results from DynamoDB
   */
  async fetchSearchResults(pdfFilename: string): Promise<PatentSearchResult[]> {
    if (!pdfFilename) {
      throw new Error("PDF filename is required");
    }

    const cleanFilename = this.cleanFilename(pdfFilename);

    return this.queueRequest(async () => {
      return this.executeWithRetry(async () => {
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
      }, "DynamoDB query");
    });
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
      try {
        const results = await this.fetchSearchResults(pdfFilename);

        if (results.length > 0) {
          return results;
        }

        // Wait before next attempt with exponential backoff for polling
        const pollDelay = Math.min(delayMs * Math.pow(1.1, attempt), 30000); // Max 30 seconds
        await this.sleep(pollDelay);
      } catch (error) {
        // If it's a rate limit error, wait longer before retrying
        if (this.isRateLimitError(error)) {
          const rateLimitDelay = Math.min(delayMs * 2, 60000); // Max 1 minute
          await this.sleep(rateLimitDelay);
        } else {
          // For other errors, use normal delay
          await this.sleep(delayMs);
        }
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
   * Get current queue status for monitoring
   */
  getQueueStatus(): { queueLength: number; isProcessing: boolean; lastRequestTime: number } {
    return {
      queueLength: this.requestQueue.length,
      isProcessing: this.isProcessingQueue,
      lastRequestTime: this.lastRequestTime
    };
  }

  /**
   * Clear the request queue (useful for cleanup)
   */
  clearQueue(): void {
    this.requestQueue.forEach(request => {
      request.reject(new Error("Request cancelled"));
    });
    this.requestQueue = [];
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
