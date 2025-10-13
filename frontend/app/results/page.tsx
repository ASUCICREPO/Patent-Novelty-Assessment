"use client";

import { useEffect, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { Header } from "@/components/Header";
import { Keywords } from "@/components/Keywords";
import { Button } from "@/components/ui/button";
import { fetchAnalysisResults, pollForResults } from "@/lib/dynamodb";
import type { ParsedAnalysisResult } from "@/types";

export default function ResultsPage() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const fileName = searchParams.get("file");

  const [results, setResults] = useState<ParsedAnalysisResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [keywords, setKeywords] = useState<string[]>([]);

  useEffect(() => {
    if (!fileName) {
      setError("No file specified");
      setLoading(false);
      return;
    }

    loadResults();
  }, [fileName]);

  const loadResults = async () => {
    if (!fileName) return;

    try {
      setLoading(true);
      setError(null);

      // Wait 15 seconds before first request to allow processing to start
      await new Promise((resolve) => setTimeout(resolve, 15000));

      // Try to fetch results after initial wait
      let result = await fetchAnalysisResults(fileName);

      // If not ready, poll for results
      if (!result || result.status !== "completed") {
        result = await pollForResults(fileName);
      }

      if (result) {
        setResults(result);
        setKeywords(result.keywords);
      } else {
        setError(
          "Analysis timed out. The document is still being processed. Please refresh the page in a few minutes to check for results."
        );
      }
    } catch (err) {
      console.error("Error loading results:", err);
      setError("Failed to load analysis results. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const handleProceedToKeywords = () => {
    // Navigate to patent search page
    router.push(`/patent-search?file=${fileName}`);
  };

  if (loading) {
    return (
      <main className="bg-white flex flex-col items-center justify-center min-h-screen w-full">
        <Header />
        <div className="flex flex-1 items-center justify-center p-16">
          <div className="text-center max-w-md">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-[#7a0019] mx-auto mb-4"></div>
            <p className="text-slate-800 mb-2 text-lg font-medium">Processing document...</p>
            <p className="text-sm text-slate-600">
              Please wait while we analyze your document. This may take a few minutes.
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
            <Button
              onClick={() => router.push("/")}
              className="bg-[#7a0019] hover:bg-[#5d0013] text-white"
            >
              Back to Upload
            </Button>
          </div>
        </div>
      </main>
    );
  }

  if (!results) {
    return (
      <main className="bg-white flex flex-col items-center justify-center min-h-screen w-full">
        <Header />
        <div className="flex flex-1 items-center justify-center p-16">
          <div className="text-center">
            <p className="text-slate-800">No results available</p>
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
                  Uploaded File: <span className="text-slate-900">{results.fileName}.pdf</span>
                </div>
                <div className="font-semibold text-base text-slate-950">
                  Title: {results.title}
                </div>
              </div>
            </div>
            
            {/* Combined Executive Summary and Key Findings */}
            <div className="border border-slate-100 box-border flex flex-col items-end justify-end p-4 rounded-2xl w-full">
              <div className="flex flex-col gap-6 items-start w-full">
                {/* Executive Summary Section */}
                <div className="flex flex-col gap-2 items-start w-full">
                  <div className="flex gap-2 items-start w-full">
                    <div className="flex flex-1 gap-2 items-center">
                      <div className="font-semibold text-base text-slate-950 whitespace-nowrap">
                        Executive Summary
                      </div>
                    </div>
                  </div>
                  <div className="font-normal text-base text-slate-800 w-full">
                    <p className="leading-6 whitespace-pre-wrap">{results.executiveSummary}</p>
                  </div>
                </div>

                {/* Key Findings Section */}
                <div className="flex flex-col gap-2 items-start w-full">
                  <div className="flex gap-2 items-start w-full">
                    <div className="flex flex-1 gap-2 items-center">
                      <div className="font-semibold text-base text-slate-950 whitespace-nowrap">
                        Key Findings
                      </div>
                    </div>
                  </div>
                  <div className="flex flex-col font-normal gap-2 items-start text-base text-slate-800 w-full">
                    {results.keyFindings.map((finding, index) => (
                      <div key={index} className="w-full whitespace-pre-wrap">
                        <span className="leading-6">{finding}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
            <Keywords 
              keywords={keywords} 
              fileName={fileName || ""} 
              onKeywordsChange={setKeywords} 
            />
          </div>

          <Button
            onClick={handleProceedToKeywords}
            className="bg-[#7a0019] hover:bg-[#5d0013] text-white font-medium text-sm px-4 py-3 rounded-lg flex items-center gap-2"
          >
            Confirm Keywords and Start Search
            <svg
              width="20"
              height="20"
              viewBox="0 0 20 20"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
            >
              <path
                d="M4.16667 10H15.8333M15.8333 10L10 4.16667M15.8333 10L10 15.8333"
                stroke="currentColor"
                strokeWidth="1.67"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </Button>
        </div>
      </div>
    </main>
  );
}
