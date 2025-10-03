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
  patent_title: string;
  application_status: string;
  filing_date: string;
  publication_date: string;
  patent_inventors: string;
  publication_number: string;
  parent_patents: number;
  relevance_score: number;
  search_strategy_used: string;
  search_timestamp: string;
  matching_keywords: string;
  specification_url: string;
  abstract_url: string;
  claims_url: string;
  specification_pages: number;
  abstract_pages: number;
  claims_pages: number;
  uspto_url: string;
  rank_position: number;
}

export interface PatentSearchResponse {
  results: PatentSearchResult[];
  totalCount: number;
  searchId: string;
  status: "searching" | "completed" | "failed";
}
