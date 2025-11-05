import type { PatentSearchResult } from "@/types";
import { getAgentInvokeApiUrl, getDynamoDBApiUrl } from "@/lib/config";

/**
 * Patent search service using API Gateway
 */
export class PatentSearchService {
  constructor() {
    // No AWS SDK initialization needed - using API Gateway
  }

  /**
   * Sleep utility function
   */
  private sleep(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  /**
   * Trigger patent search using unified agent endpoint
   */
  async triggerPatentSearch(pdfFilename: string): Promise<string> {
    if (!pdfFilename) {
      throw new Error("PDF filename is required");
    }

    try {
      const response = await fetch(getAgentInvokeApiUrl(), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ 
          action: 'search_patents',
          pdfFilename 
        }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || 'Failed to trigger patent search');
      }

      const result = await response.json();
      return result.sessionId;
    } catch (error) {
      console.error("Error triggering patent search:", error);
      throw error;
    }
  }

  /**
   * Fetch patent search results using unified DynamoDB endpoint
   */
  async fetchSearchResults(pdfFilename: string): Promise<PatentSearchResult[]> {
    if (!pdfFilename) {
      throw new Error("PDF filename is required");
    }

    try {
      const response = await fetch(`${getDynamoDBApiUrl()}?tableType=patent-results&pdfFilename=${encodeURIComponent(pdfFilename)}`);
      
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || 'Failed to fetch patent search results');
      }

      const result = await response.json();
      return result.results as PatentSearchResult[];
    } catch (error) {
      console.error("Error fetching patent search results:", error);
      throw error;
    }
  }

  /**
   * Check if filename count has reached the expected number (8) before polling
   */
  async checkFilenameCount(pdfFilename: string, expectedCount: number = 8): Promise<{ reached: boolean; count: number }> {
    try {
      const response = await fetch(`${getDynamoDBApiUrl()}?tableType=patent-results&pdfFilename=${encodeURIComponent(pdfFilename)}`);
      
      if (!response.ok) {
        console.error("Error checking filename count:", response.statusText);
        return { reached: false, count: 0 };
      }

      const result = await response.json();
      const count = result.count || 0;
      
      console.log(`Filename count for ${pdfFilename}: ${count}/${expectedCount}`);
      return { reached: count >= expectedCount, count };
    } catch (error) {
      console.error("Error checking filename count:", error);
      return { reached: false, count: 0 };
    }
  }

  /**
   * Poll for search results until they're available
   * Stops after maxAttempts (default 20, which is 10 minutes with 30s delay)
   * Returns results along with status information
   */
  async pollForSearchResults(
    pdfFilename: string,
    delayMs: number = 30000, // 30 seconds between polls
    expectedFilenameCount: number = 8,
    maxAttempts: number = 20 // 20 attempts = 10 minutes
  ): Promise<{ results: PatentSearchResult[]; stoppedEarly: boolean; finalCount: number }> {
    // Poll until filename count reaches expected number or max attempts reached
    console.log(`Waiting for filename count to reach ${expectedFilenameCount} (max ${maxAttempts} attempts)...`);
    let attempts = 0;
    let currentCount = 0;
    
    while (attempts < maxAttempts) {
      try {
        const { reached, count } = await this.checkFilenameCount(pdfFilename, expectedFilenameCount);
        currentCount = count;
        attempts++;
        
        if (reached) {
          console.log(`Filename count reached ${expectedFilenameCount} after ${attempts} attempts, fetching results...`);
          break;
        }
        
        console.log(`Count not yet reached (${count}/${expectedFilenameCount}), attempt ${attempts}/${maxAttempts}, waiting ${delayMs/1000} seconds...`);
        
        // Wait before next count check (only if not at max attempts)
        if (attempts < maxAttempts) {
          await this.sleep(delayMs);
        }
      } catch (error) {
        console.error("Error during count check:", error);
        attempts++;
        if (attempts < maxAttempts) {
          await this.sleep(delayMs);
        }
      }
    }
    
    const stoppedEarly = attempts >= maxAttempts && currentCount < expectedFilenameCount;
    
    if (stoppedEarly) {
      console.log(`Polling stopped after ${maxAttempts} attempts. Current count: ${currentCount}/${expectedFilenameCount}`);
    }
    
    // Fetch actual results
    console.log("Fetching search results...");
    try {
      const results = await this.fetchSearchResults(pdfFilename);
      console.log(`Found ${results.length} search results`);
      return { results, stoppedEarly, finalCount: currentCount };
    } catch (error) {
      console.error("Error fetching search results:", error);
      return { results: [], stoppedEarly, finalCount: currentCount };
    }
  }

  /**
   * Update add_to_report field for a patent using unified DynamoDB endpoint
   */
  async updateAddToReport(pdfFilename: string, patentNumber: string, addToReport: boolean): Promise<void> {
    try {
      const response = await fetch(getDynamoDBApiUrl(), {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          operation: 'update_add_to_report',
          tableType: 'patent-results',
          pdfFilename,
          patentNumber,
          addToReport,
        }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || 'Failed to update add_to_report');
      }

      const result = await response.json();
      console.log(result.message);
    } catch (error) {
      console.error("Error updating add_to_report:", error);
      throw error;
    }
  }

}

// Export a singleton instance
export const patentSearchService = new PatentSearchService();
