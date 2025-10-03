"use client";

import { useState, useCallback } from "react";
import AWS from "aws-sdk";
import type { UploadedFile, UploadProgress } from "@/types";

interface UseFileUploadReturn {
  uploadedFile: UploadedFile | null;
  progress: UploadProgress | null;
  error: string | null;
  isUploading: boolean;
  uploadFile: (file: File) => Promise<void>;
  resetUpload: () => void;
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


      setProgress({
        percentage: 10,
        stage: "uploading",
        message: "Preparing upload...",
      });

      // Configure AWS S3
      const s3 = new AWS.S3({
        accessKeyId: process.env.NEXT_PUBLIC_AWS_ACCESS_KEY_ID,
        secretAccessKey: process.env.NEXT_PUBLIC_AWS_SECRET_ACCESS_KEY,
        region: process.env.NEXT_PUBLIC_AWS_REGION || 'us-west-2',
      });

      const bucketName = process.env.NEXT_PUBLIC_S3_BUCKET;
      if (!bucketName) {
        throw new Error("S3 bucket not configured. Please set NEXT_PUBLIC_S3_BUCKET in .env.local");
      }

      const s3Key = `uploads/${file.name}`;

      setProgress({
        percentage: 50,
        stage: "uploading",
        message: "Uploading to S3...",
      });

      // Upload directly to S3 using putObject for better CORS compatibility
      const uploadParams = {
        Bucket: bucketName,
        Key: s3Key,
        Body: file,
        ContentType: file.type,
        ACL: 'private', // Make sure it's private
      };

      // Use putObject instead of upload for better CORS handling
      await s3.putObject(uploadParams).promise();

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

      // Set uploaded file
      setUploadedFile({
        file,
        name: file.name,
        size: file.size,
        type: file.type,
        uploadedAt: new Date(),
      });

      // Redirect to results page after successful upload
      if (typeof window !== "undefined") {
        // Give a moment for the user to see the success message
        setTimeout(() => {
          window.location.href = `/results?file=${encodeURIComponent(file.name)}`;
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