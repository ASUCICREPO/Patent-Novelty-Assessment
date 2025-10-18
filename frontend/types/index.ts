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
  add_to_report?: string;
  backward_citations?: number;
  citations?: number;
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
}

// Scholarly Article Types
export interface ScholarlyArticle {
  pdf_filename: string;
  article_doi: string;
  add_to_report?: string;
  abstract: string;
  article_title: string;
  article_type?: string;
  article_url: string;
  authors: string;
  citation_count: number;
  fields_of_study: string;
  journal: string;
  key_technical_overlaps: string;
  llm_decision?: string;
  llm_reasoning?: string;
  matching_keywords: string;
  novelty_impact_assessment: string;
  open_access_pdf_url: string;
  published_date: string;
  relevance_score: number;
  search_query_used: string;
  search_timestamp: string;
}
