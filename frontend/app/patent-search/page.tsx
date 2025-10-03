"use client";

import { useEffect, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { Header } from "@/components/Header";
import { PatentSearchResults } from "@/components/PatentSearchResults";
import { fetchAnalysisResults } from "@/lib/dynamodb";
import type { ParsedAnalysisResult } from "@/types";

export default function PatentSearchPage() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const fileName = searchParams.get("file");

  const [analysisResults, setAnalysisResults] = useState<ParsedAnalysisResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [keywords, setKeywords] = useState<string[]>([]);

  useEffect(() => {
    if (!fileName) {
      setError("No file specified");
      setLoading(false);
      return;
    }

    loadAnalysisResults();
  }, [fileName]);

  const loadAnalysisResults = async () => {
    if (!fileName) return;

    try {
      setLoading(true);
      setError(null);

      const result = await fetchAnalysisResults(fileName);
      
      if (result) {
        setAnalysisResults(result);
        setKeywords(result.keywords);
      } else {
        setError("Analysis results not found. Please go back and try again.");
      }
    } catch (err) {
      console.error("Error loading analysis results:", err);
      setError("Failed to load analysis results. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const handleKeywordsChange = (newKeywords: string[]) => {
    setKeywords(newKeywords);
  };

  const handleRefineKeywords = () => {
    // Navigate back to keywords page or show keyword refinement modal
    router.push(`/results?file=${fileName}`);
  };


  if (loading) {
    return (
      <main className="bg-white flex flex-col items-center justify-center min-h-screen w-full">
        <Header />
        <div className="flex flex-1 items-center justify-center p-16">
          <div className="text-center max-w-md">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-[#7a0019] mx-auto mb-4"></div>
            <p className="text-slate-800 mb-2">Loading analysis results...</p>
            <p className="text-sm text-slate-600">
              Please wait while we prepare your patent search.
            </p>
          </div>
        </div>
      </main>
    );
  }

  if (error) {
    return (
      <main className="bg-white flex flex-col items-center justify-center min-h-screen w-full">
        <Header />
        <div className="flex flex-1 items-center justify-center p-16">
          <div className="text-center max-w-md">
            <p className="text-red-600 mb-4">{error}</p>
            <button
              onClick={() => router.push("/")}
              className="bg-[#7a0019] hover:bg-[#5d0013] text-white px-4 py-2 rounded-lg"
            >
              Back to Upload
            </button>
          </div>
        </div>
      </main>
    );
  }

  if (!analysisResults) {
    return (
      <main className="bg-white flex flex-col items-center justify-center min-h-screen w-full">
        <Header />
        <div className="flex flex-1 items-center justify-center p-16">
          <div className="text-center">
            <p className="text-slate-800">No analysis results available</p>
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className="bg-white flex flex-col items-center min-h-screen w-full">
      <Header />
      <div className="border-t border-slate-100 box-border flex flex-1 flex-col items-center w-full px-16 py-10">
        <div className="flex flex-1 flex-col gap-10 items-end w-full max-w-6xl">
          <div className="flex flex-col gap-6 items-start w-full">
            {/* File and Title Section */}
            <div className="border border-slate-100 box-border flex flex-col items-end justify-end p-4 rounded-2xl w-full">
              <div className="flex flex-col gap-2 items-start w-full">
                <div className="text-sm font-medium text-slate-600">
                  Uploaded File: <span className="text-slate-900">{analysisResults.fileName}.pdf</span>
                </div>
                <div className="font-semibold text-base text-slate-950">
                  Title: {analysisResults.title}
                </div>
              </div>
            </div>
            
            {/* Patent Search Results */}
            <PatentSearchResults
              keywords={keywords}
              fileName={fileName || ""}
              onKeywordsChange={handleKeywordsChange}
              onRefineKeywords={handleRefineKeywords}
            />
          </div>
        </div>
      </div>
    </main>
  );
}
