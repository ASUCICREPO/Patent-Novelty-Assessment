"use client";

import { useState, useEffect, useRef } from "react";
import { Button } from "@/components/ui/button";
import { scholarlySearchService } from "@/lib/scholarlySearch";
import type { ScholarlyArticle } from "@/types";

interface LiteratureSearchResultsProps {
  keywords: string[];
  fileName: string;
  onKeywordsChange: (keywords: string[]) => void;
}

export function LiteratureSearchResults({
  keywords,
  fileName,
  onKeywordsChange,
}: LiteratureSearchResultsProps) {
  const [searchResults, setSearchResults] = useState<ScholarlyArticle[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searching, setSearching] = useState(false);
  const hasTriggeredSearch = useRef(false);

  useEffect(() => {
    if (fileName && keywords.length > 0 && !hasTriggeredSearch.current) {
      hasTriggeredSearch.current = true;
      triggerSearch();
    }
  }, [fileName]);

  const triggerSearch = async () => {
    try {
      setLoading(true);
      setSearching(true);
      setError(null);

      // First, trigger the literature search via Agent Core
      console.log("Triggering literature search via Agent Core...");
      await scholarlySearchService.triggerScholarlySearch(fileName);
      
      // Wait for 2 minutes for the search to complete
      console.log("Waiting 2 minutes for search to complete...");
      setError("Search initiated. Please wait 2 minutes for results to be processed...");
      
      // Wait 2 minutes
      await new Promise(resolve => setTimeout(resolve, 120000));
      
      console.log("2 minutes elapsed, starting to poll for results...");
      setError("Search completed. Fetching results...");
      
      // Now start polling for results with 30-second intervals
      const results = await scholarlySearchService.pollForSearchResults(fileName);
      
      if (results.length > 0) {
        setSearchResults(results);
        setError(null);
      } else {
        setError("No scholarly articles found matching your keywords. Try refining your search terms.");
      }
    } catch (err) {
      console.error("Error during literature search:", err);
      const errorMessage = err instanceof Error ? err.message : String(err);
      setError(`Failed to search literature: ${errorMessage}`);
    } finally {
      setLoading(false);
      setSearching(false);
    }
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
    
    const keywordRegex = new RegExp(`\\b(${keywords.join('|')})\\b`, 'gi');
    const parts = text.split(keywordRegex);
    const matches = text.match(keywordRegex) || [];
    
    return parts.map((part, index) => {
      if (index < matches.length) {
        return (
          <span key={index}>
            {part}
            <span className="font-medium text-[#7a0019]">{matches[index]}</span>
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
          <p className="text-slate-800 mb-2">Searching scholarly articles...</p>
          <p className="text-sm text-slate-600">
            Please wait while we find relevant academic literature.
          </p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[400px] w-full">
        <div className="text-center max-w-md">
          <p className="text-red-600 mb-4">{error}</p>
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
      <div className="bg-white border border-slate-100 rounded-lg w-full">
        <div className="flex flex-col gap-3 items-start p-4 w-full">
          <p className="font-semibold text-base text-slate-950">
            Search Keywords
          </p>
          <div className="flex gap-2 items-center w-full">
            <div className="flex gap-2 items-center flex-wrap">
              {keywords.map((keyword, index) => (
                <div
                  key={index}
                  className="bg-gray-50 border border-slate-200 flex items-center justify-center px-2.5 py-1 rounded-lg"
                >
                  <p className="font-medium text-sm text-slate-800">
                    {keyword}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Relevant Academic Literature Section */}
      <div className="border border-slate-100 rounded-lg w-full">
        <div className="flex flex-col gap-4 items-start p-4">
          <p className="font-semibold text-base text-slate-950">
            Relevant Academic Literature
          </p>
          
          {searchResults.length === 0 ? (
            <div className="flex flex-col items-center justify-center p-8 w-full">
              <p className="text-slate-600 text-center">
                No scholarly articles found. Try refining your keywords or check back later.
              </p>
            </div>
          ) : (
            <div className="flex flex-col gap-4 w-full">
              {searchResults.map((article, index) => (
                <div
                  key={article.article_doi}
                  className="border border-slate-100 flex flex-col gap-4 items-end justify-end p-4 rounded-xl w-full"
                >
                  <div className="flex flex-col gap-2 items-start w-full">
                    <div className="flex gap-2 items-start w-full">
                      <div className="flex flex-1 items-start min-h-0 min-w-0">
                        <a
                          href={article.open_access_pdf_url || article.article_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="font-semibold text-base text-slate-950 underline decoration-solid underline-offset-[25%] hover:text-[#7a0019] transition-colors"
                        >
                          {article.article_title}
                          <span className="inline-block ml-1">
                            <svg
                              width="16"
                              height="16"
                              viewBox="0 0 20 20"
                              fill="none"
                              xmlns="http://www.w3.org/2000/svg"
                              className="inline"
                            >
                              <path
                                d="M10 6.66667H4.16667C3.24619 6.66667 2.5 7.41286 2.5 8.33333V15.8333C2.5 16.7538 3.24619 17.5 4.16667 17.5H11.6667C12.5871 17.5 13.3333 16.7538 13.3333 15.8333V10M7.5 2.5H17.5M17.5 2.5V12.5M17.5 2.5L7.5 12.5"
                                stroke="currentColor"
                                strokeWidth="1.67"
                                strokeLinecap="round"
                                strokeLinejoin="round"
                              />
                            </svg>
                          </span>
                        </a>
                      </div>
                      <button className="border border-slate-200 flex gap-1 items-center justify-center px-2 py-1.5 rounded shrink-0 hover:bg-slate-50">
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
                      {article.abstract}
                    </p>
                  </div>
                  
                  {/* Novelty Assessment section */}
                  <div className="bg-[#fff7f9] flex gap-2 items-center justify-center p-3 rounded-lg w-full">
                    <p className="flex-1 font-normal text-base text-slate-800 whitespace-pre-wrap">
                      {article.novelty_impact_assessment || "No novelty assessment provided for this article."}
                    </p>
                  </div>
                  
                  {/* Article details */}
                  <div className="flex flex-col font-normal gap-1 items-start text-sm text-slate-600 w-full whitespace-pre-wrap">
                    <p>Authors: {article.authors}</p>
                    <p>Published in: {article.journal}</p>
                    <p>Published: {formatDate(article.published_date)}</p>
                    {/* DOI removed per requirements */}
                    <p>Citations: {article.citation_count}</p>
                    <p>Relevance Score: {article.relevance_score?.toFixed(2) || "N/A"}</p>
                  </div>


                  {/* Dedicated Novelty Impact Assessment section removed per requirements */}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Action Buttons */}
      <div className="flex gap-4 items-start justify-end w-full">
        <Button
          className="bg-[#7a0019] hover:bg-[#5d0013] text-white flex items-center gap-1"
        >
          Generate Final Reports
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
  );
}
