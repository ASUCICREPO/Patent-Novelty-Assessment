import { getAgentInvokeApiUrl, getS3ApiUrl } from "@/lib/config";

/**
 * Report generation service using API Gateway
 */
export class ReportGenerationService {
  constructor() {
    // No environment variables needed - all AWS resources are handled via API Gateway
  }

  /**
   * Trigger report generation using unified agent endpoint
   */
  async triggerReportGeneration(pdfFilename: string): Promise<string> {
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
          action: 'generate_report',
          pdfFilename 
        }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || 'Failed to trigger report generation');
      }

      const result = await response.json();
      return result.sessionId;
    } catch (error) {
      console.error("Error triggering report generation:", error);
      throw error;
    }
  }

  /**
   * Check if reports are ready using unified S3 endpoint
   */
  async checkReportsReady(pdfFilename: string): Promise<{ ptlsReady: boolean; ecaReady: boolean }> {
    try {
      const cleanFilename = this.cleanFilename(pdfFilename);
      
      console.log(`Checking reports via unified S3 API for: ${cleanFilename}`);
      
      // Use unified S3 API to check file existence
      const response = await fetch(`${getS3ApiUrl()}?operation=check_reports&filename=${encodeURIComponent(cleanFilename)}`);
      
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
   * Get download URLs for the generated reports using unified S3 endpoint
   * Since files are not publicly accessible, we'll use the API to get signed URLs
   */
  async getReportDownloadUrls(pdfFilename: string): Promise<{ ptlsUrl: string; ecaUrl: string }> {
    try {
      const cleanFilename = this.cleanFilename(pdfFilename);
      
      // Use unified S3 API to get signed URLs
      const response = await fetch(`${getS3ApiUrl()}?operation=get_signed_urls&filename=${encodeURIComponent(cleanFilename)}`);
      
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
      throw new Error("Failed to get report download URLs. Please try again later.");
    }
  }

  /**
   * Clean filename by removing PDF extension
   */
  private cleanFilename(filename: string): string {
    return filename.replace(/\.pdf$/i, "");
  }
}

// Export a singleton instance
export const reportGenerationService = new ReportGenerationService();
