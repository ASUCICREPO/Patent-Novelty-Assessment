import type { PatentAnalysisResult, ParsedAnalysisResult } from "@/types";
import { getDynamoDBApiUrl } from "@/lib/config";

/**
 * Fetch patent analysis results using unified DynamoDB endpoint
 */
export async function fetchAnalysisResults(
  fileName: string
): Promise<ParsedAnalysisResult | null> {
  try {
    const response = await fetch(`${getDynamoDBApiUrl()}?tableType=analysis&fileName=${encodeURIComponent(fileName)}`);
    
    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(errorData.error || 'Failed to fetch analysis results');
    }

    const result = await response.json();
    
    if (!result.result) {
      return null;
    }

    const item = result.result as PatentAnalysisResult;
    return parseAnalysisResult(item);
  } catch (error) {
    console.error("Error fetching analysis results:", error);
    throw error;
  }
}

/**
 * Parse DynamoDB result into a more user-friendly format
 */
function parseAnalysisResult(
  item: PatentAnalysisResult
): ParsedAnalysisResult {
  // Use technology description as executive summary
  const executiveSummary = item.technology_description;

  // Parse keywords into an array
  const keywords = item.keywords
    .split(",")
    .map((k) => k.trim())
    .filter((k) => k.length > 0);

  // Generate key findings with technology applications
  const keyFindings = generateKeyFindings(item);

  return {
    fileName: item.pdf_filename,
    timestamp: item.timestamp,
    title: item.title,
    executiveSummary,
    keyFindings,
    keywords,
    status: item.processing_status,
  };
}

/**
 * Generate key findings from the analysis result
 * Technology applications is shown as "Key Application"
 */
function generateKeyFindings(item: PatentAnalysisResult): string[] {
  const findings: string[] = [];

  // Add technology applications as "Key Application"
  if (item.technology_applications) {
    findings.push(item.technology_applications);
  }

  return findings;
}

/**
 * Update keywords using unified DynamoDB endpoint
 */
export async function updateKeywords(
  fileName: string,
  keywords: string[]
): Promise<void> {
  try {
    const response = await fetch(getDynamoDBApiUrl(), {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        operation: 'update_keywords',
        tableType: 'analysis',
        fileName,
        keywords,
      }),
    });

    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(errorData.error || 'Failed to update keywords');
    }

    const result = await response.json();
    console.log(result.message);
  } catch (error) {
    console.error("Error updating keywords:", error);
    throw error;
  }
}

/**
 * Poll DynamoDB for results until they're available
 */
export async function pollForResults(
  fileName: string,
  maxAttempts: number = 60, // Increased from 30 to 60 (2 minutes total)
  delayMs: number = 2000
): Promise<ParsedAnalysisResult | null> {
  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    const result = await fetchAnalysisResults(fileName);

    if (result) {
      if (result.status === "completed") {
        return result;
      } else if (result.status === "failed") {
        throw new Error("Document processing failed");
      }
      // If status is "processing" or "pending", continue polling
    }

    // Wait before next attempt
    await new Promise((resolve) => setTimeout(resolve, delayMs));
  }

  return null; // Timeout
}
