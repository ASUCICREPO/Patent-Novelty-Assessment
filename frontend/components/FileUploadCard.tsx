"use client";

import { useState, useRef } from "react";
import { Button } from "@/components/ui/button";
import { UploadIcon } from "./UploadIcon";
import { useFileUpload } from "@/hooks/useFileUpload";

export function FileUploadCard() {
  const [isDragging, setIsDragging] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const { uploadFile, isUploading, progress, error } = useFileUpload();

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    
    const files = e.dataTransfer.files;
    
    // Only accept single PDF file
    if (files.length !== 1) {
      alert("Please upload only one file at a time.");
      return;
    }
    
    const file = files[0];
    if (file.type !== "application/pdf") {
      alert("Only PDF files are supported. Please upload a PDF file.");
      return;
    }
    
    setSelectedFile(file);
    // Auto-upload immediately
    await uploadFile(file);
  };

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    
    if (!files || files.length === 0) {
      return;
    }
    
    // Only accept single PDF file
    if (files.length > 1) {
      alert("Please upload only one file at a time.");
      return;
    }
    
    const file = files[0];
    if (file.type !== "application/pdf") {
      alert("Only PDF files are supported. Please upload a PDF file.");
      e.target.value = ""; // Reset input
      return;
    }
    
    setSelectedFile(file);
    // Auto-upload immediately
    await uploadFile(file);
  };

  const handleBrowseClick = () => {
    if (!isUploading) {
      fileInputRef.current?.click();
    }
  };

  return (
    <div className="flex flex-col gap-6 items-center relative shrink-0 w-full">
      <div
        className={`bg-white box-border flex flex-col items-center p-8 relative rounded-2xl shrink-0 w-[480px] border border-dashed transition-colors ${
          isDragging ? "border-[#7a0019] bg-[#fff7f9]" : "border-slate-200"
        }`}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        <div className="flex flex-col gap-8 items-center relative shrink-0 w-full">
          <div className="flex flex-col gap-4 items-start relative shrink-0 w-full">
            <div className="flex flex-col gap-4 items-center relative shrink-0 w-full">
              <div className="bg-[#fff7f9] flex gap-2 items-center p-2 relative rounded-lg shrink-0">
                <UploadIcon />
              </div>
              <div className="font-semibold min-w-full relative shrink-0 text-base text-center text-slate-950">
                {selectedFile ? selectedFile.name : "Upload File"}
              </div>
            </div>
            <div className="flex flex-col gap-2 items-center text-sm text-center w-full">
              <div className="font-medium relative shrink-0 text-slate-950 w-full">
                Drop the file here or click to browse
              </div>
              <div className="font-normal relative shrink-0 text-slate-600 w-full">
                Supports PDF (.pdf) file
              </div>
            </div>
          </div>
          
          {/* Progress indicator */}
          {progress && (
            <div className="w-full">
              <div className="flex justify-between text-xs text-slate-600 mb-2">
                <span>{progress.message}</span>
                <span>{progress.percentage}%</span>
              </div>
              <div className="w-full bg-slate-200 rounded-full h-2">
                <div
                  className="bg-[#7a0019] h-2 rounded-full transition-all duration-300"
                  style={{ width: `${progress.percentage}%` }}
                />
              </div>
            </div>
          )}
          
          {/* Error message */}
          {error && (
            <div className="w-full p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-600">
              {error}
            </div>
          )}
          
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,application/pdf"
            onChange={handleFileSelect}
            className="hidden"
            disabled={isUploading}
          />
          <Button
            onClick={handleBrowseClick}
            disabled={isUploading}
            className="bg-[#7a0019] hover:bg-[#5d0013] disabled:opacity-50 disabled:cursor-not-allowed text-white font-medium text-sm px-4 py-3 rounded-lg w-full h-auto transition-colors"
          >
            {isUploading ? "Uploading..." : "Upload File"}
          </Button>
        </div>
      </div>
    </div>
  );
}
