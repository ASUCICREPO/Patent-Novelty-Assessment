"use client";

import { useState, useEffect, useRef, useMemo } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { patentSearchService } from "@/lib/patentSearch";
import { statePersistence } from "@/lib/statePersistence";
import type { PatentSearchResult } from "@/types";

interface PatentSearchResultsProps {
  keywords: string[];
  fileName: string;
  onKeywordsChange: (keywords: string[]) => void;
}

export function PatentSearchResults({
  keywords,
  fileName,
}: PatentSearchResultsProps) {
  const router = useRouter();
  const [searchResults, setSearchResults] = useState<PatentSearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searching, setSearching] = useState(false);
  const [updatingReports, setUpdatingReports] = useState<Set<string>>(new Set());
  const hasTriggeredSearch = useRef(false);
  const hasInitialized = useRef(false);
  const searchStateKey = useMemo(() => `patent_${fileName}`, [fileName]);

  useEffect(() => {
    if (!fileName || keywords.length === 0) return;

    // Check for existing search state on component mount
    const existingState = statePersistence.getState(searchStateKey);
    
    if (existingState) {
      // Check if cached state has results - if not, clear it and start fresh
      if (existingState.results && existingState.results.length === 0 && !existingState.isSearching) {
        console.log("Cached state has no results, clearing and starting fresh search");
        statePersistence.clearState(searchStateKey);
        hasTriggeredSearch.current = false;
        hasInitialized.current = false;
        // Fall through to trigger new search
      } else {
        // Restore state from localStorage
        setSearchResults((existingState.results as PatentSearchResult[]) || []);
        setError(existingState.error);
        
        if (existingState.isSearching) {
          setSearching(true);
          setLoading(true);
        }
        
        // Mark as triggered to prevent duplicate triggers
        hasTriggeredSearch.current = existingState.hasTriggered;
        
        // If search was in progress, just show the UI - don't restart the search
        if (statePersistence.shouldResumeSearch(searchStateKey)) {
          console.log("Page refreshed - resuming polling for existing search results...");
          // Resume polling immediately on refresh (no retrigger, no 5-min wait)
          checkForCompletedSearch();
        }
        
        // Mark as initialized to prevent re-triggering
        hasInitialized.current = true;
      }
    }
    
    // Trigger new search if no existing state or if we cleared empty cached state
    if (!existingState || (existingState.results && existingState.results.length === 0 && !existingState.isSearching)) {
      if (!hasTriggeredSearch.current && !hasInitialized.current && keywords.length > 0) {
        hasTriggeredSearch.current = true;
        hasInitialized.current = true;
        executeSearch();
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fileName, keywords.length]);

  // Cleanup function to clear state when component unmounts
  useEffect(() => {
    return () => {
      // Only clear state if search is completed (not in progress)
      const currentState = statePersistence.getState(searchStateKey);
      if (currentState && !currentState.isSearching) {
        statePersistence.clearState(searchStateKey);
      }
    };
  }, [searchStateKey]);

  const checkForCompletedSearch = async () => {
    // Check if search results are now available in the database
    try {
      setLoading(true);
      setSearching(true);
      setError("Checking for search results...");
      
      console.log("Polling for search results...");
      const results = await patentSearchService.pollForSearchResults(fileName);
      
      if (results.length > 0) {
        setSearchResults(results);
        setError(null);
        
        // Update state with results
        statePersistence.setState(searchStateKey, {
          results: results,
          isSearching: false,
          error: null,
          lastPollTime: Date.now()
        });
        
        console.log(`Found ${results.length} search results`);
      } else {
        setError("No patents found matching your keywords. Try refining your search terms.");
        statePersistence.setState(searchStateKey, {
          isSearching: false,
          error: "No patents found matching your keywords. Try refining your search terms."
        });
      }
    } catch (err) {
      console.error("Error checking for search results:", err);
      const errorMessage = err instanceof Error ? err.message : String(err);
      setError(`Failed to get search results: ${errorMessage}`);
      statePersistence.setState(searchStateKey, {
        isSearching: false,
        error: `Failed to get search results: ${errorMessage}`
      });
    } finally {
      setLoading(false);
      setSearching(false);
    }
  };

  const executeSearch = async () => {
    // Single search execution function - no time calculations, no makeshift logic
    try {
      setLoading(true);
      setSearching(true);
      setError("Search initiated. This may take a few minutes to process...");
      
      // Persist initial search state
      statePersistence.setState(searchStateKey, {
        hasTriggered: true,
        isSearching: true,
        searchStartTime: Date.now(),
        lastPollTime: Date.now(),
        retryCount: 0,
        error: "Search initiated. This may take a few minutes to process...",
        results: []
      });

      // Trigger the patent search via Agent Core
      console.log("Triggering patent search via Agent Core...");
      patentSearchService.triggerPatentSearch(fileName);
      
      // Wait for 5 minutes for the search to complete
      console.log("Waiting 5 minutes for search to complete...");
      setError("Search initiated. This may take a few minutes to process...");
      
      // Update state during wait
      statePersistence.setState(searchStateKey, {
        error: "Search initiated. This may take a few minutes to process...",
        lastPollTime: Date.now()
      });
      
      // Wait 5 minutes
      await new Promise(resolve => setTimeout(resolve, 300000));
      
      console.log("5 minutes elapsed, starting to poll for results...");
      setError("Search completed. Fetching results...");
      
      // Update state before polling
      statePersistence.setState(searchStateKey, {
        error: "Search completed. Fetching results...",
        lastPollTime: Date.now()
      });
      
      // Start polling for results
      const results = await patentSearchService.pollForSearchResults(fileName);
      
      if (results.length > 0) {
        setSearchResults(results);
        setError(null);
        
        // Persist successful results
        statePersistence.setState(searchStateKey, {
          results: results,
          isSearching: false,
          error: null,
          lastPollTime: Date.now()
        });
      } else {
        setError("No patents found matching your keywords. Try refining your search terms.");
        statePersistence.setState(searchStateKey, {
          isSearching: false,
          error: "No patents found matching your keywords. Try refining your search terms."
        });
      }
    } catch (err) {
      console.error("Error during search process:", err);
      const errorMessage = err instanceof Error ? err.message : String(err);
      setError(`Failed to search patents: ${errorMessage}`);
      
      // Persist error state
      statePersistence.setState(searchStateKey, {
        isSearching: false,
        error: `Failed to search patents: ${errorMessage}`
      });
    } finally {
      setLoading(false);
      setSearching(false);
    }
  };

  const triggerSearch = async () => {
    // Use the single search execution function
    await executeSearch();
  };

  const handleProceedToLiteratureSearch = () => {
    router.push(`/literature-search?file=${fileName}`);
  };

  const handleAddToReport = async (patentNumber: string, currentStatus: string) => {
    try {
      setUpdatingReports(prev => new Set(prev).add(patentNumber));
      
      const newStatus = currentStatus === "Yes" ? false : true;
      await patentSearchService.updateAddToReport(fileName, patentNumber, newStatus);
      
      // Update the local state
      setSearchResults(prev => prev.map(patent => 
        patent.patent_number === patentNumber 
          ? { ...patent, add_to_report: newStatus ? "Yes" : "No" }
          : patent
      ));
    } catch (error) {
      console.error("Error updating add to report:", error);
      // You could add a toast notification here
    } finally {
      setUpdatingReports(prev => {
        const newSet = new Set(prev);
        newSet.delete(patentNumber);
        return newSet;
      });
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

  if (loading || searching) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[500px] w-full">
        <div className="flex flex-col gap-10 items-center w-full max-w-[480px] px-8">
          <div className="flex flex-col gap-2 items-center text-center">
            <p className="font-semibold text-2xl text-slate-950">
              Patent Database Search
            </p>
            <p className="text-base text-slate-800 w-[400px] whitespace-pre-wrap">
              Searching patent databases for relevant patents and intellectual property
            </p>
          </div>
          
          <div className="flex flex-col gap-6 items-center w-full">
            <div className="border border-dashed border-slate-200 rounded-2xl p-8 w-full">
              <div className="flex flex-col gap-6 items-center w-full">
                <div className="flex flex-col gap-4 items-center w-full">
                  <div className="bg-[#fff7f9] flex items-center justify-center p-2 rounded-lg">
                    <div className="w-10 h-10 flex items-center justify-center">
                      <svg className="w-6 h-6 text-[#7a0019]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                      </svg>
                    </div>
                  </div>
                  <p className="font-semibold text-base text-center text-slate-950">
                    Searching Patent Database
                  </p>
                </div>
                
                <div className="flex flex-col gap-4 items-center w-full">
                  <div className="flex items-center justify-center w-full">
                    <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-[#7a0019]"></div>
                  </div>
                  <div className="flex items-center justify-center w-full">
                    <p className="font-medium text-sm text-slate-600 text-center">
                      Searching... Please wait
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[400px] w-full">
        <div className="text-center max-w-md">
          <div className="mb-4">
            <div className="text-red-600">
              <svg className="w-8 h-8 mx-auto mb-2" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
              </svg>
              <p className="text-lg font-medium">Search Error</p>
            </div>
          </div>
          <p className="text-slate-800 mb-4 text-sm">{error}</p>
          <Button
            onClick={() => {
              // Clear existing state and start fresh
              statePersistence.clearState(searchStateKey);
              hasTriggeredSearch.current = false;
              triggerSearch();
            }}
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
              {searchResults.map((patent) => (
                <div
                  key={patent.patent_number}
                  className="border border-slate-100 flex flex-col gap-4 items-end justify-end p-4 rounded-xl w-full"
                >
                  <div className="flex flex-col gap-2 items-start w-full">
                    <div className="flex gap-2 items-center w-full">
                      <div className="flex flex-1 gap-2 items-center min-h-0 min-w-0">
                        <a
                          href={patent.google_patents_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="font-semibold text-base text-slate-950 underline decoration-solid underline-offset-[25%] hover:text-[#7a0019] transition-colors"
                        >
                          {patent.patent_title}
                        </a>
                        <a
                          href={patent.google_patents_url}
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
                      <button 
                        onClick={() => handleAddToReport(patent.patent_number, patent.add_to_report || "No")}
                        disabled={updatingReports.has(patent.patent_number)}
                        className={`border flex gap-1 items-center justify-center px-2 py-1.5 rounded shrink-0 transition-colors w-36 ${
                          patent.add_to_report === "Yes" 
                            ? "border-[#7a0019] hover:bg-slate-50" 
                            : "border-[#7a0019] bg-[#7a0019] text-white hover:bg-[#5d0013]"
                        } ${updatingReports.has(patent.patent_number) ? "opacity-50 cursor-not-allowed" : ""}`}
                      >
                        <p className="font-medium text-sm">
                          {patent.add_to_report === "Yes" ? "Remove" : "Add to Report"}
                        </p>
                        <svg
                          width="16"
                          height="16"
                          viewBox="0 0 16 16"
                          fill="none"
                          xmlns="http://www.w3.org/2000/svg"
                        >
                          <path
                            d={patent.add_to_report === "Yes" ? "M4 8H12" : "M8 4V12M4 8H12"}
                            stroke="currentColor"
                            strokeWidth="1.33"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                          />
                        </svg>
                      </button>
                    </div>
                    <div className="h-48 overflow-y-auto w-full">
                      <p className="font-normal text-base text-slate-800 whitespace-pre-wrap">
                        {patent.patent_abstract || `${patent.patent_title} - Patent #${patent.patent_number}`}
                      </p>
                    </div>
                  </div>
                  
                  {/* LLM Notes section */}
                  <div className="bg-[#fff7f9] flex gap-2 items-center justify-center p-3 rounded-lg w-full">
                    <p className="flex-1 font-normal text-base text-slate-800 whitespace-pre-wrap">
                      {patent.llm_examiner_notes || "No examiner notes provided for this patent."}
                    </p>
                  </div>
                  
                  {/* Patent details */}
                  <div className="flex flex-col font-normal gap-1 items-start text-sm text-slate-600 w-full whitespace-pre-wrap">
                    <p>Patent: {patent.patent_number}</p>
                    <p>Inventors: {patent.patent_inventors}</p>
                    <p>Filing Date: {formatDate(patent.filing_date || "")}</p>
                    <p>Grant Date: {formatDate(patent.grant_date || "")}</p>
                    <p>Publication Date: {formatDate(patent.publication_date || "")}</p>
                    <p>Citations: {patent.citation_count}</p>
                    <p>Backward Citations: {patent.backward_citations}</p>
                    {patent.relevance_score && (
                      <p>Relevance: {patent.relevance_score}</p>
                    )}
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
