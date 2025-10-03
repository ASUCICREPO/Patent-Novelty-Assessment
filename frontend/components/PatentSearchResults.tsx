"use client";

import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { patentSearchService } from "@/lib/patentSearch";
import type { PatentSearchResult } from "@/types";

interface PatentSearchResultsProps {
  keywords: string[];
  fileName: string;
  onKeywordsChange: (keywords: string[]) => void;
  onRefineKeywords: () => void;
}

export function PatentSearchResults({
  keywords,
  fileName,
  onKeywordsChange,
  onRefineKeywords,
}: PatentSearchResultsProps) {
  const [searchResults, setSearchResults] = useState<PatentSearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searching, setSearching] = useState(false);

  useEffect(() => {
    if (fileName && keywords.length > 0) {
      triggerSearch();
    }
  }, [fileName, keywords]);

  const triggerSearch = async () => {
    try {
      setLoading(true);
      setSearching(true);
      setError(null);

      // Trigger the search
      await patentSearchService.triggerPatentSearch(fileName);

      // Poll for results
      const results = await patentSearchService.pollForSearchResults(fileName);
      setSearchResults(results);
      
      if (results.length === 0) {
        setError("No patents found matching your keywords. Try refining your search terms.");
      }
    } catch (err) {
      console.error("Error during patent search:", err);
      setError("Failed to search patents. Please check your AWS credentials and try again.");
    } finally {
      setLoading(false);
      setSearching(false);
    }
  };

  const removeKeyword = (keywordToRemove: string) => {
    const updatedKeywords = keywords.filter(k => k !== keywordToRemove);
    onKeywordsChange(updatedKeywords);
  };

  const formatDate = (dateString: string) => {
    if (!dateString) return "N/A";
    try {
      return new Date(dateString).toLocaleDateString("en-US", {
        month: "numeric",
        day: "numeric",
        year: "numeric",
      });
    } catch {
      return dateString;
    }
  };

  const highlightKeywords = (text: string) => {
    if (!keywords.length) return text;
    
    const keywordRegex = new RegExp(`(${keywords.join("|")})`, "gi");
    const parts = text.split(keywordRegex);
    
    return parts.map((part, index) => {
      const isKeyword = keywords.some(k => 
        part.toLowerCase() === k.toLowerCase()
      );
      
      if (isKeyword) {
        return (
          <span key={index} className="font-medium text-[#7a0019]">
            {part}
          </span>
        );
      }
      return part;
    });
  };

  if (loading || searching) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[400px] w-full">
        <div className="text-center max-w-md">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-[#7a0019] mx-auto mb-4"></div>
          <p className="text-slate-800 mb-2 text-lg font-medium">Searching patents...</p>
          <p className="text-sm text-slate-600">
            This may take a few minutes while we search through patent databases.
          </p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[400px] w-full">
        <div className="text-center max-w-md">
          <p className="text-red-600 mb-4 text-lg font-medium">{error}</p>
          <Button
            onClick={triggerSearch}
            className="bg-[#7a0019] hover:bg-[#5d0013] text-white"
          >
            Retry Search
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6 items-start w-full">
      {/* Search Keywords Section */}
      <div className="bg-white border border-slate-100 rounded-2xl w-full">
        <div className="flex flex-col gap-4 items-start p-4 w-full">
          <p className="font-semibold text-base text-slate-950">
            Search Keywords
          </p>
          <div className="flex gap-2 items-center w-full">
            <div className="flex gap-2 items-center flex-wrap">
              {keywords.map((keyword, index) => (
                <div
                  key={index}
                  className="bg-gray-50 border border-slate-200 flex gap-1 items-center justify-center pl-2.5 pr-1.5 py-1 rounded-lg"
                >
                  <div className="flex gap-1.5 items-center">
                    <p className="font-medium text-sm text-slate-800">
                      {keyword}
                    </p>
                  </div>
                  <button
                    onClick={() => removeKeyword(keyword)}
                    className="flex items-center justify-center p-0.5 rounded-sm hover:bg-gray-200"
                  >
                    <svg
                      width="12"
                      height="12"
                      viewBox="0 0 12 12"
                      fill="none"
                      xmlns="http://www.w3.org/2000/svg"
                    >
                      <path
                        d="M9 3L3 9M3 3L9 9"
                        stroke="currentColor"
                        strokeWidth="1.5"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      />
                    </svg>
                  </button>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Relevant Patents Section */}
      <div className="border border-slate-100 flex-1 min-h-0 min-w-0 rounded-lg w-full">
        <div className="flex flex-col gap-4 items-start p-4 h-full">
          <p className="font-semibold text-base text-slate-950">
            Relevant Patents
          </p>
          
          {searchResults.length === 0 ? (
            <div className="flex flex-col items-center justify-center p-8 w-full">
              <p className="text-slate-600 text-center">
                No patents found. Try refining your keywords or check back later.
              </p>
            </div>
          ) : (
            <div className="flex flex-col gap-4 w-full">
              {searchResults.map((patent, index) => (
                <div
                  key={patent.patent_number}
                  className="border border-slate-100 flex flex-col gap-4 items-end justify-end p-4 rounded-2xl w-full"
                >
                  <div className="flex flex-col gap-2 items-start w-full">
                    <div className="flex gap-2 items-center w-full">
                      <div className="flex flex-1 gap-2 items-center min-h-0 min-w-0">
                        <p className="font-semibold text-base text-slate-950 underline decoration-solid underline-offset-[25%]">
                          {patent.patent_title}
                        </p>
                        <a
                          href={patent.uspto_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="shrink-0 w-5 h-5"
                        >
                          <svg
                            width="20"
                            height="20"
                            viewBox="0 0 20 20"
                            fill="none"
                            xmlns="http://www.w3.org/2000/svg"
                          >
                            <path
                              d="M10 6.66667H4.16667C3.24619 6.66667 2.5 7.41286 2.5 8.33333V15.8333C2.5 16.7538 3.24619 17.5 4.16667 17.5H11.6667C12.5871 17.5 13.3333 16.7538 13.3333 15.8333V10M7.5 2.5H17.5M17.5 2.5V12.5M17.5 2.5L7.5 12.5"
                              stroke="currentColor"
                              strokeWidth="1.67"
                              strokeLinecap="round"
                              strokeLinejoin="round"
                            />
                          </svg>
                        </a>
                      </div>
                      <button className="border border-slate-200 flex gap-1 items-center justify-center px-2 py-1.5 rounded shrink-0">
                        <p className="font-medium text-sm text-slate-800">
                          View Citations
                        </p>
                        <svg
                          width="16"
                          height="16"
                          viewBox="0 0 16 16"
                          fill="none"
                          xmlns="http://www.w3.org/2000/svg"
                        >
                          <path
                            d="M8 1.33333V14.6667M8 1.33333L14.6667 8M8 1.33333L1.33333 8"
                            stroke="currentColor"
                            strokeWidth="1.33"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                          />
                        </svg>
                      </button>
                      <button className="border border-slate-200 flex gap-1 items-center justify-center px-2 py-1.5 rounded shrink-0">
                        <p className="font-medium text-sm text-slate-800">
                          Add to Report
                        </p>
                        <svg
                          width="16"
                          height="16"
                          viewBox="0 0 16 16"
                          fill="none"
                          xmlns="http://www.w3.org/2000/svg"
                        >
                          <path
                            d="M8 1.33333V14.6667M8 1.33333L14.6667 8M8 1.33333L1.33333 8"
                            stroke="currentColor"
                            strokeWidth="1.33"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                          />
                        </svg>
                      </button>
                    </div>
                    <p className="font-normal text-base text-slate-800 w-full whitespace-pre-wrap">
                      {patent.patent_title} - Patent #{patent.patent_number}
                    </p>
                  </div>
                  
                  {/* Keyword highlighting section */}
                  <div className="bg-[#fff7f9] flex gap-2 items-center justify-center p-3 rounded-lg w-full">
                    <p className="flex-1 font-normal text-base text-slate-800 whitespace-pre-wrap">
                      {highlightKeywords(
                        `The invention relates to ${patent.patent_title} and involves ${patent.matching_keywords || "patent technology"}.`
                      )}
                    </p>
                  </div>
                  
                  {/* Patent details */}
                  <div className="flex flex-col font-normal gap-1 items-start text-sm text-slate-600 w-full whitespace-pre-wrap">
                    <p>Patent: {patent.patent_number}</p>
                    <p>Status: {patent.application_status}</p>
                    <p>Published: {formatDate(patent.publication_date)}</p>
                    <p>Inventors: {patent.patent_inventors}</p>
                    <p>Relevance Score: {patent.relevance_score?.toFixed(2) || "N/A"}</p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Action Buttons */}
      <div className="flex gap-4 items-start justify-end w-full">
        <Button
          onClick={onRefineKeywords}
          variant="outline"
          className="border-slate-200 text-slate-950 hover:bg-slate-50"
        >
          Refine Keywords
        </Button>
      </div>
    </div>
  );
}
