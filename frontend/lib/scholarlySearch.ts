import type { ScholarlyArticle } from "@/types";
import { getAgentInvokeApiUrl, getDynamoDBApiUrl } from "@/lib/config";

export class ScholarlySearchService {
  constructor() {
    // No AWS SDK initialization needed - using API Gateway
  }

  /**
   * Trigger scholarly article search via unified agent endpoint
   */
  async triggerScholarlySearch(pdfFilename: string): Promise<string> {
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
          action: 'search_articles',
          pdfFilename 
        }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || 'Failed to trigger scholarly search');
      }

      const result = await response.json();
      return result.sessionId;
    } catch (error) {
      console.error("Error triggering scholarly search:", error);
      throw error;
    }
  }

  /**
   * Fetch scholarly article search results using unified DynamoDB endpoint
   */
  async fetchSearchResults(pdfFilename: string): Promise<ScholarlyArticle[]> {
    try {
      const response = await fetch(`${getDynamoDBApiUrl()}?tableType=scholarly-results&pdfFilename=${encodeURIComponent(pdfFilename)}`);
      
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || 'Failed to fetch scholarly search results');
      }

      const result = await response.json();
      return result.results as ScholarlyArticle[];
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
      const response = await fetch(`${getDynamoDBApiUrl()}?tableType=scholarly-results&pdfFilename=${encodeURIComponent(pdfFilename)}`);
      
      if (!response.ok) {
        console.error("Error checking filename count:", response.statusText);
        return false;
      }

      const result = await response.json();
      const count = result.count || 0;
      
      console.log(`Filename count for ${pdfFilename}: ${count}/${expectedCount}`);
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
   * Update add_to_report field for a scholarly article using unified DynamoDB endpoint
   */
  async updateAddToReport(pdfFilename: string, articleDoi: string, addToReport: boolean): Promise<void> {
    try {
      const response = await fetch(getDynamoDBApiUrl(), {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          operation: 'update_add_to_report',
          tableType: 'scholarly-results',
          pdfFilename,
          articleDoi,
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

  /**
   * Sleep utility function
   */
  private sleep(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms));
  }
}

export const scholarlySearchService = new ScholarlySearchService();
