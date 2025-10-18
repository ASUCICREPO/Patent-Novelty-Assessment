"use client";

import { useState, useCallback } from "react";
import { S3Client, PutObjectCommand } from "@aws-sdk/client-s3";
import type { UploadedFile, UploadProgress } from "@/types";

interface UseFileUploadReturn {
  uploadedFile: UploadedFile | null;
  progress: UploadProgress | null;
  error: string | null;
  isUploading: boolean;
  uploadFile: (file: File) => Promise<void>;
  resetUpload: () => void;
}

/**
 * Sanitize file name for safe S3 upload
 * - Replaces spaces with underscores
 * - Removes or replaces special characters
 * - Preserves the .pdf extension
 */
function sanitizeFileName(fileName: string): string {
  // Split name and extension
  const lastDotIndex = fileName.lastIndexOf('.');
  const name = lastDotIndex > -1 ? fileName.substring(0, lastDotIndex) : fileName;
  const extension = lastDotIndex > -1 ? fileName.substring(lastDotIndex) : '';
  
  // Sanitize the name part
  let sanitized = name
    // Replace spaces with underscores
    .replace(/\s+/g, '_')
    // Remove or replace special characters
    .replace(/[&@+=#%]/g, '_')  // Replace common special chars with underscore
    .replace(/[<>:"|?*]/g, '')   // Remove invalid filename characters
    .replace(/[^\w\-_.]/g, '_')  // Replace any other non-alphanumeric chars (except - _ .) with underscore
    // Remove consecutive underscores
    .replace(/_+/g, '_')
    // Remove leading/trailing underscores
    .replace(/^_+|_+$/g, '');
  
  // If sanitization resulted in empty string, use a default name
  if (!sanitized) {
    sanitized = 'document';
  }
  
  return sanitized + extension.toLowerCase();
}

export function useFileUpload(): UseFileUploadReturn {
  const [uploadedFile, setUploadedFile] = useState<UploadedFile | null>(null);
  const [progress, setProgress] = useState<UploadProgress | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);

  const uploadFile = useCallback(async (file: File) => {
    setError(null);
    setIsUploading(true);

    try {
      // Validate file type
      if (file.type !== "application/pdf") {
        throw new Error("Only PDF files are supported");
      }

      // Sanitize the file name
      const sanitizedFileName = sanitizeFileName(file.name);


      setProgress({
        percentage: 10,
        stage: "uploading",
        message: "Preparing upload...",
      });

      // Configure AWS S3 (v3)
      const s3Client = new S3Client({
        region: process.env.NEXT_PUBLIC_AWS_REGION || 'us-west-2',
        credentials: {
          accessKeyId: process.env.NEXT_PUBLIC_AWS_ACCESS_KEY_ID || "",
          secretAccessKey: process.env.NEXT_PUBLIC_AWS_SECRET_ACCESS_KEY || "",
        },
      });

      const bucketName = process.env.NEXT_PUBLIC_S3_BUCKET;
      if (!bucketName) {
        throw new Error("S3 bucket not configured. Please set NEXT_PUBLIC_S3_BUCKET in .env.local");
      }

      // Use sanitized file name for S3 key
      const s3Key = `uploads/${sanitizedFileName}`;

      setProgress({
        percentage: 50,
        stage: "uploading",
        message: `Uploading ${sanitizedFileName}...`,
      });

      // Upload directly to S3 using putObject for better CORS compatibility
      // Convert file to a Uint8Array to avoid ReadableStream issues in browsers
      const fileBuffer = new Uint8Array(await file.arrayBuffer());

      const uploadParams = {
        Bucket: bucketName,
        Key: s3Key,
        Body: fileBuffer,
        ContentType: file.type,
      };

      // Use PutObjectCommand in AWS SDK v3
      await s3Client.send(new PutObjectCommand(uploadParams));

      setProgress({
        percentage: 80,
        stage: "processing",
        message: "Upload complete! Processing...",
      });

      await new Promise((resolve) => setTimeout(resolve, 1000));

      setProgress({
        percentage: 100,
        stage: "complete",
        message: "File uploaded successfully!",
      });

      // Set uploaded file with sanitized name
      setUploadedFile({
        file,
        name: sanitizedFileName,
        size: file.size,
        type: file.type,
        uploadedAt: new Date(),
      });

      // Redirect to results page after successful upload with sanitized file name
      if (typeof window !== "undefined") {
        // Give a moment for the user to see the success message
        setTimeout(() => {
          window.location.href = `/results?file=${encodeURIComponent(sanitizedFileName)}`;
        }, 1500);
      }
    } catch (err) {
      console.error('Upload error:', err);
      
      // Check if it's a CORS error
      if (err instanceof Error && err.message.includes('CORS')) {
        setError("CORS error: Please check S3 bucket CORS configuration. The bucket needs to allow requests from this domain.");
      } else if (err instanceof Error && err.message.includes('Access-Control-Allow-Origin')) {
        setError("CORS error: S3 bucket is not configured to allow uploads from this domain. Please contact administrator.");
      } else {
        setError(err instanceof Error ? err.message : "Upload failed. Please try again.");
      }
      
      setProgress(null);
    } finally {
      setIsUploading(false);
    }
  }, []);

  const resetUpload = useCallback(() => {
    setUploadedFile(null);
    setProgress(null);
    setError(null);
    setIsUploading(false);
  }, []);

  return {
    uploadedFile,
    progress,
    error,
    isUploading,
    uploadFile,
    resetUpload,
  };
}