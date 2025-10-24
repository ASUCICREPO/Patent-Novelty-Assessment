"use client";

import { useState, useCallback } from "react";
import type { UploadedFile, UploadProgress } from "@/types";
import { getS3ApiUrl } from "@/lib/config";

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

      setProgress({
        percentage: 50,
        stage: "uploading",
        message: `Uploading ${file.name}...`,
      });

      // Get presigned URL for direct S3 upload (bypasses API Gateway)
      const presignedResponse = await fetch(`${getS3ApiUrl()}?operation=get_presigned_url&filename=${encodeURIComponent(file.name)}`);
      
      if (!presignedResponse.ok) {
        const errorData = await presignedResponse.json();
        throw new Error(errorData.error || 'Failed to get presigned URL');
      }
      
      const presignedData = await presignedResponse.json();
      const { uploadUrl, fileName, s3Key, bucket } = presignedData;
      
      // Upload directly to S3 using presigned URL
      const response = await fetch(uploadUrl, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/pdf',
        },
        body: file,
      });

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`Upload failed: ${response.status} ${errorText}`);
      }

      // Presigned URL upload to S3 returns empty response on success
      // We already have the file info from the presigned URL response

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
        name: fileName,
        size: file.size,
        type: file.type,
        uploadedAt: new Date(),
      });

      // Redirect to results page after successful upload with sanitized file name
      if (typeof window !== "undefined") {
        // Give a moment for the user to see the success message
        setTimeout(() => {
          window.location.href = `/results?file=${encodeURIComponent(fileName)}`;
        }, 1500);
      }
    } catch (err) {
      console.error('Upload error:', err);
      setError(err instanceof Error ? err.message : "Upload failed. Please try again.");
      setProgress(null);
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