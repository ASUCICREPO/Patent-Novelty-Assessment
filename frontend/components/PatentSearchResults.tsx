"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { patentSearchService } from "@/lib/patentSearch";
import type { PatentSearchResult } from "@/types";

interface PatentSearchResultsProps {
  keywords: string[];
  fileName: string;
  onKeywordsChange: (keywords: string[]) => void;
}

export function PatentSearchResults({
  keywords,
  fileName,
  onKeywordsChange,
}: PatentSearchResultsProps) {
  const router = useRouter();
  const [searchResults, setSearchResults] = useState<PatentSearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searching, setSearching] = useState(false);
  const [retryCount, setRetryCount] = useState(0);
  const [isRateLimited, setIsRateLimited] = useState(false);
  const [queueStatus, setQueueStatus] = useState({ queueLength: 0, isProcessing: false, lastRequestTime: 0 });

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
      setRetryCount(0);
      setIsRateLimited(false);

      // Update queue status
      setQueueStatus(patentSearchService.getQueueStatus());

      // Skip triggering since results are already in the database
      // Try direct fetch first to see if results are already there
      const results = await patentSearchService.fetchSearchResults(fileName);
      
      if (results.length > 0) {
        // Found results immediately, no need to poll
      } else {
        // No immediate results, start polling
        const polledResults = await patentSearchService.pollForSearchResults(fileName);
        results.push(...polledResults);
      }
      
      if (results.length > 0) {
        setSearchResults(results);
        setIsRateLimited(false);
        setRetryCount(0);
      } else {
        setError("No patents found matching your keywords. Try refining your search terms.");
      }
    } catch (err) {
      console.error("Error during patent search:", err);
      const errorMessage = err instanceof Error ? err.message : String(err);
      
      if (errorMessage.includes("429") || errorMessage.includes("Too Many Requests") || errorMessage.includes("Rate limit")) {
        setIsRateLimited(true);
        setError("Search is temporarily rate limited. Please wait a moment and try again.");
      } else {
        setError("Failed to search patents. Please check your AWS credentials and try again.");
      }
    } finally {
      setLoading(false);
      setSearching(false);
    }
  };

  const removeKeyword = (keywordToRemove: string) => {
    const updatedKeywords = keywords.filter(k => k !== keywordToRemove);
    onKeywordsChange(updatedKeywords);
  };

  const handleProceedToLiteratureSearch = () => {
    router.push(`/literature-search?file=${fileName}`);
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
          <p className="text-slate-800 mb-2 text-lg font-medium">
            {isRateLimited ? "Rate limited - waiting..." : "Searching patents..."}
          </p>
          <p className="text-sm text-slate-600 mb-2">
            {isRateLimited 
              ? "Too many requests. We're waiting before retrying..."
              : "This may take a few minutes while we search through patent databases."
            }
          </p>
          {retryCount > 0 && (
            <p className="text-xs text-slate-500">
              Attempt {retryCount}/30
            </p>
          )}
          {queueStatus.queueLength > 0 && (
            <p className="text-xs text-slate-500">
              {queueStatus.queueLength} request(s) in queue
            </p>
          )}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[400px] w-full">
        <div className="text-center max-w-md">
          <div className="mb-4">
            {isRateLimited ? (
              <div className="text-orange-600 mb-2">
                <svg className="w-8 h-8 mx-auto mb-2" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                </svg>
                <p className="text-lg font-medium">Rate Limited</p>
              </div>
            ) : (
              <div className="text-red-600">
                <svg className="w-8 h-8 mx-auto mb-2" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                </svg>
                <p className="text-lg font-medium">Search Error</p>
              </div>
            )}
          </div>
          <p className="text-slate-800 mb-4 text-sm">{error}</p>
          {isRateLimited && (
            <p className="text-xs text-slate-500 mb-4">
              The patent search service is experiencing high traffic. Please wait a moment before retrying.
            </p>
          )}
          <Button
            onClick={triggerSearch}
            className={`${isRateLimited 
              ? 'bg-orange-600 hover:bg-orange-700' 
              : 'bg-[#7a0019] hover:bg-[#5d0013]'
            } text-white`}
            disabled={isRateLimited && retryCount < 3}
          >
            {isRateLimited ? 'Wait and Retry' : 'Retry Search'}
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
                  className="bg-gray-50 border border-slate-200 flex items-center justify-center px-2 py-1 rounded-md"
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
                  className="border border-slate-100 flex flex-col gap-4 items-end justify-end p-4 rounded-xl w-full"
                >
                  <div className="flex flex-col gap-2 items-start w-full">
                    <div className="flex gap-2 items-center w-full">
                      <div className="flex flex-1 gap-2 items-center min-h-0 min-w-0">
                        <a
                          href={patent.google_patents_url || patent.uspto_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="font-semibold text-base text-slate-950 underline decoration-solid underline-offset-[25%] hover:text-[#7a0019] transition-colors"
                        >
                          {patent.patent_title}
                        </a>
                        <a
                          href={patent.google_patents_url || patent.uspto_url}
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
                      {patent.patent_abstract || `${patent.patent_title} - Patent #${patent.patent_number}`}
                    </p>
                  </div>
                  
                  {/* Keyword highlighting section */}
                  <div className="bg-[#fff7f9] flex gap-2 items-center justify-center p-3 rounded-lg w-full">
                    <p className="flex-1 font-normal text-base text-slate-800 whitespace-pre-wrap">
                      {highlightKeywords(
                        `The invention relates to ${patent.patent_title || "this patent"} and involves ${patent.matching_keywords || "patent technology"}.`
                      )}
                    </p>
                  </div>
                  
                  {/* Patent details */}
                  <div className="flex flex-col font-normal gap-1 items-start text-sm text-slate-600 w-full whitespace-pre-wrap">
                    <p>Patent: {patent.patent_number}</p>
                    {patent.forward_citations && patent.backward_citations && (
                      <p>Forward Citations: {patent.forward_citations} | Backward Citations: {patent.backward_citations}</p>
                    )}
                    <p>Published: {formatDate(patent.publication_date || "")}</p>
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
          onClick={handleProceedToLiteratureSearch}
          className="bg-[#7a0019] hover:bg-[#5d0013] text-white flex items-center gap-1"
        >
          Proceed to Literature Search
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
