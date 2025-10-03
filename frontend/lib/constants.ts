/**
 * Application-wide constants
 */

export const APP_NAME = "Patent Search Tool";
export const ORGANIZATION = "University of Minnesota";

export const FILE_UPLOAD = {
  MAX_SIZE: 10 * 1024 * 1024, // 10MB
  ACCEPTED_TYPES: ["application/pdf"],
  ACCEPTED_EXTENSIONS: [".pdf"],
} as const;

export const COLORS = {
  UMN_MAROON: "#7A0019",
  UMN_GOLD: "#FFCC33",
  UMN_LIGHT_PINK: "#FFF7F9",
} as const;

export const API_ENDPOINTS = {
  UPLOAD: "/api/upload",
  ANALYZE: "/api/analyze",
  RESULTS: "/api/results",
} as const;

export const ROUTES = {
  HOME: "/",
  RESULTS: "/results",
  ANALYSIS: "/analysis",
} as const;
