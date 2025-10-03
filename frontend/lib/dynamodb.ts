import AWS from "aws-sdk";
import type { PatentAnalysisResult, ParsedAnalysisResult } from "@/types";

/**
 * Fetch patent analysis results from DynamoDB
 */
export async function fetchAnalysisResults(
  fileName: string
): Promise<ParsedAnalysisResult | null> {
  try {
    // Configure AWS DynamoDB
    const dynamodb = new AWS.DynamoDB.DocumentClient({
      accessKeyId: process.env.NEXT_PUBLIC_AWS_ACCESS_KEY_ID,
      secretAccessKey: process.env.NEXT_PUBLIC_AWS_SECRET_ACCESS_KEY,
      region: process.env.NEXT_PUBLIC_AWS_REGION || "us-west-2",
    });

    const tableName =
      process.env.NEXT_PUBLIC_DYNAMODB_TABLE || "patent-keywords";

    // Query DynamoDB for the results
    const params = {
      TableName: tableName,
      KeyConditionExpression: "pdf_filename = :filename",
      ExpressionAttributeValues: {
        ":filename": fileName.replace(/\.pdf$/i, ""),
      },
      ScanIndexForward: false, // Get most recent first
      Limit: 1,
    };

    const result = await dynamodb.query(params).promise();

    if (!result.Items || result.Items.length === 0) {
      return null;
    }

    const item = result.Items[0] as unknown as PatentAnalysisResult;

    // Parse the results into a more usable format
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
 * Update keywords in DynamoDB
 */
export async function updateKeywords(
  fileName: string,
  keywords: string[]
): Promise<void> {
  try {
    // Configure AWS DynamoDB
    const dynamodb = new AWS.DynamoDB.DocumentClient({
      accessKeyId: process.env.NEXT_PUBLIC_AWS_ACCESS_KEY_ID,
      secretAccessKey: process.env.NEXT_PUBLIC_AWS_SECRET_ACCESS_KEY,
      region: process.env.NEXT_PUBLIC_AWS_REGION || "us-west-2",
    });

    const tableName =
      process.env.NEXT_PUBLIC_DYNAMODB_TABLE || "patent-keywords";

    // First, find the item to get its full key structure
    const queryParams = {
      TableName: tableName,
      KeyConditionExpression: "pdf_filename = :filename",
      ExpressionAttributeValues: {
        ":filename": fileName.replace(/\.pdf$/i, ""),
      },
      Limit: 1,
    };

    const queryResult = await dynamodb.query(queryParams).promise();

    if (!queryResult.Items || queryResult.Items.length === 0) {
      throw new Error("Item not found in DynamoDB");
    }

    const item = queryResult.Items[0];

    // Build the key dynamically based on what we find
    const key: any = {
      pdf_filename: item.pdf_filename,
    };

    // Add any additional key fields that might exist
    // Common DynamoDB patterns: timestamp, id, sk (sort key), etc.
    if (item.timestamp) {
      key.timestamp = item.timestamp;
    }
    if (item.id) {
      key.id = item.id;
    }
    if (item.sk) {
      key.sk = item.sk;
    }

    // Update the keywords field using the full key structure
    const updateParams = {
      TableName: tableName,
      Key: key,
      UpdateExpression: "SET keywords = :keywords",
      ExpressionAttributeValues: {
        ":keywords": keywords.join(", "),
      },
      ReturnValues: "UPDATED_NEW",
    };

    await dynamodb.update(updateParams).promise();
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
