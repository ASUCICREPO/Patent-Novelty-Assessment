/**
 * Application configuration
 * Reads from environment variables
 */

export const config = {
  api: {
    url: process.env.NEXT_PUBLIC_API_URL || "http://localhost:3001",
    key: process.env.NEXT_PUBLIC_API_KEY || "",
  },
  aws: {
    region: process.env.NEXT_PUBLIC_AWS_REGION || "us-east-1",
    s3Bucket: process.env.NEXT_PUBLIC_S3_BUCKET || "",
  },
  features: {
    enableAnalytics: process.env.NEXT_PUBLIC_ENABLE_ANALYTICS === "true",
    enableDebug: process.env.NEXT_PUBLIC_ENABLE_DEBUG === "true",
  },
  upload: {
    maxFileSize:
      parseInt(process.env.NEXT_PUBLIC_MAX_FILE_SIZE || "10485760", 10),
    allowedFileTypes:
      process.env.NEXT_PUBLIC_ALLOWED_FILE_TYPES?.split(",") || [
        "application/pdf",
      ],
  },
} as const;
