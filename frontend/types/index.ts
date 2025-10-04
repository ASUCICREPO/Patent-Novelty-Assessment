/**
 * Type definitions for the Patent Search Tool
 */

export interface UploadedFile {
  file: File;
  name: string;
  size: number;
  type: string;
  uploadedAt: Date;
}

export interface AnalysisResult {
  id: string;
  fileName: string;
  status: "pending" | "processing" | "completed" | "failed";
  noveltyScore?: number;
  commercializationScore?: number;
  insights?: string[];
  similarPatents?: Patent[];
  uploadedAt: Date;
  completedAt?: Date;
}

export interface Patent {
  id: string;
  title: string;
  patentNumber: string;
  publicationDate: string;
  inventors: string[];
  abstract: string;
  similarityScore: number;
}

export interface UploadProgress {
  percentage: number;
  stage: "uploading" | "processing" | "analyzing" | "complete";
  message: string;
}

// DynamoDB Result Types
export interface PatentAnalysisResult {
  pdf_filename: string;
  timestamp: string;
  title: string;
  technology_description: string;
  technology_applications: string;
  keywords: string;
  processing_status: string;
}

export interface ParsedAnalysisResult {
  fileName: string;
  timestamp: string;
  title: string;
  executiveSummary: string;
  keyFindings: string[];
  keywords: string[];
  status: string;
}

// Patent Search Result Types
export interface PatentSearchResult {
  pdf_filename: string;
  patent_number: string;
  backward_citations?: number;
  citation_count?: number;
  filing_date?: string;
  foreign_citations?: number;
  forward_citations?: number;
  google_patents_url?: string;
  grant_date?: string;
  key_differences?: string;
  llm_examiner_notes?: string;
  matching_keywords?: string;
  patent_abstract?: string;
  patent_assignees?: string;
  patent_inventors?: string;
  patent_title?: string;
  publication_date?: string;
  publication_number?: string;
  relevance_score?: number;
  search_timestamp?: string;
  // Legacy fields for backward compatibility
  application_status?: string;
  uspto_url?: string;
}

export interface PatentSearchResponse {
  results: PatentSearchResult[];
  totalCount: number;
  searchId: string;
  status: "searching" | "completed" | "failed";
}
