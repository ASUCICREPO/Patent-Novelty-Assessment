"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Header } from "@/components/Header";
import { reportGenerationService } from "@/lib/reportGeneration";

export default function ReportGenerationPage() {
  const searchParams = useSearchParams();
  const fileName = searchParams.get("file");

  const [reportsReady, setReportsReady] = useState({ ptlsReady: false, ecaReady: false });
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (fileName) {
      checkReportsStatus();
    }
  }, [fileName]);

  const checkReportsStatus = async () => {
    if (!fileName) return;
    
    try {
      const status = await reportGenerationService.checkReportsReady(fileName);
      setReportsReady(status);
    } catch (err) {
      console.error("Error checking reports status:", err);
    }
  };

  const triggerReportGeneration = async () => {
    if (!fileName) return;

    try {
      setGenerating(true);
      setError(null);
      
      await reportGenerationService.triggerReportGeneration(fileName);
      
      // Start polling for reports to be ready
      const pollInterval = setInterval(async () => {
        try {
          const status = await reportGenerationService.checkReportsReady(fileName);
          setReportsReady(status);
          
          if (status.ptlsReady && status.ecaReady) {
            clearInterval(pollInterval);
            setGenerating(false);
          }
        } catch (err) {
          console.error("Error polling for reports:", err);
        }
      }, 5000); // Check every 5 seconds

      // Clear interval after 5 minutes
      setTimeout(() => {
        clearInterval(pollInterval);
        setGenerating(false);
      }, 300000);

    } catch (err) {
      console.error("Error generating reports:", err);
      setError("Failed to generate reports. Please try again.");
      setGenerating(false);
    }
  };

  const handleDownload = async (reportType: 'ptls' | 'eca') => {
    if (!fileName) return;
    
    try {
      const urls = await reportGenerationService.getReportDownloadUrls(fileName);
      const url = reportType === 'ptls' ? urls.ptlsUrl : urls.ecaUrl;
      
      // Open download link in new tab
      window.open(url, '_blank');
    } catch (error) {
      console.error('Error getting download URL:', error);
    }
  };

  if (!fileName) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen">
        <p className="text-red-600">No file specified</p>
      </div>
    );
  }

  return (
    <main className="bg-white min-h-screen w-full">
      <Header />
      <div className="border-t border-slate-100 w-full">
        <div className="flex flex-col items-center px-16 py-30">
          <div className="flex flex-col gap-10 items-center w-full max-w-2xl">
            {/* Header Section */}
            <div className="flex flex-col gap-2 items-center text-center">
              <h1 className="text-xl font-semibold text-slate-950">Report Generation</h1>
              <p className="text-base text-slate-800 max-w-md">
                AI-powered report generation of combined patent and literature search results
              </p>
            </div>

            {/* Report Cards Section */}
            <div className="flex flex-col gap-4 w-full">
              {/* PTLS Report Card */}
              <div className="bg-gray-50 border border-slate-300 rounded-2xl p-4 w-full">
                <div className="flex flex-col gap-6 items-end w-full">
                  <div className="flex flex-col gap-4 items-start w-full">
                    <div className="flex flex-col gap-2 items-start">
                      <div className="flex gap-2 items-center">
                        <div className="w-6 h-6 flex items-center justify-center">
                          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                            <path d="M14 2H6C4.9 2 4 2.9 4 4V20C4 21.1 4.89 22 5.99 22H18C19.1 22 20 21.1 20 20V8L14 2Z" stroke="#7a0019" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                            <path d="M14 2V8H20" stroke="#7a0019" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                            <path d="M16 13H8" stroke="#7a0019" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                            <path d="M16 17H8" stroke="#7a0019" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                            <path d="M10 9H8" stroke="#7a0019" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                          </svg>
                        </div>
                        <p className="text-sm font-semibold text-slate-950">
                          Prior Art & Technology Landscape Search (PTLS) Report
                        </p>
                      </div>
                      <p className="text-sm text-slate-800">
                        Analysis of existing patents and academic literature relevant to your invention
                      </p>
                    </div>
                  </div>
                  
                  {reportsReady.ptlsReady ? (
                    <button
                      onClick={() => handleDownload('ptls')}
                      className="bg-[#7a0019] hover:bg-[#5d0013] text-white flex items-center gap-1 px-3 py-1.5 rounded text-sm font-medium"
                    >
                      Download
                      <svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
                        <path d="M8 1.33333V10.6667M8 10.6667L5.33333 8M8 10.6667L10.6667 8M2.66667 12.6667H13.3333" stroke="currentColor" strokeWidth="1.33" strokeLinecap="round" strokeLinejoin="round"/>
                      </svg>
                    </button>
                  ) : (
                    <div className="flex items-center gap-2 text-slate-500">
                      <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-slate-400"></div>
                      <span className="text-sm">Generating...</span>
                    </div>
                  )}
                </div>
              </div>

              {/* ECA Report Card */}
              <div className="bg-gray-50 border border-slate-300 rounded-2xl p-4 w-full">
                <div className="flex flex-col gap-6 items-end w-full">
                  <div className="flex flex-col gap-4 items-start w-full">
                    <div className="flex flex-col gap-2 items-start">
                      <div className="flex gap-2 items-center">
                        <div className="w-6 h-6 flex items-center justify-center">
                          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                            <path d="M14 2H6C4.9 2 4 2.9 4 4V20C4 21.1 4.89 22 5.99 22H18C19.1 22 20 21.1 20 20V8L14 2Z" stroke="#7a0019" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                            <path d="M14 2V8H20" stroke="#7a0019" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                            <path d="M16 13H8" stroke="#7a0019" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                            <path d="M16 17H8" stroke="#7a0019" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                            <path d="M10 9H8" stroke="#7a0019" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                          </svg>
                        </div>
                        <p className="text-sm font-semibold text-slate-950">
                          Early Commercialization Assessment (ECA) Report
                        </p>
                      </div>
                      <p className="text-sm text-slate-800">
                        Market analysis and commercialization potential evaluation for your invention
                      </p>
                    </div>
                  </div>
                  
                  {reportsReady.ecaReady ? (
                    <button
                      onClick={() => handleDownload('eca')}
                      className="bg-[#7a0019] hover:bg-[#5d0013] text-white flex items-center gap-1 px-3 py-1.5 rounded text-sm font-medium"
                    >
                      Download
                      <svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
                        <path d="M8 1.33333V10.6667M8 10.6667L5.33333 8M8 10.6667L10.6667 8M2.66667 12.6667H13.3333" stroke="currentColor" strokeWidth="1.33" strokeLinecap="round" strokeLinejoin="round"/>
                      </svg>
                    </button>
                  ) : (
                    <div className="flex items-center gap-2 text-slate-500">
                      <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-slate-400"></div>
                      <span className="text-sm">Generating...</span>
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Generate Button (when no reports ready) */}
            {!reportsReady.ptlsReady && !reportsReady.ecaReady && !generating && (
              <div className="flex justify-center w-full">
                <button
                  onClick={triggerReportGeneration}
                  className="bg-[#7a0019] hover:bg-[#5d0013] text-white flex items-center gap-2 px-6 py-3 rounded-lg font-medium"
                >
                  Generate Reports
                  <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path d="M4.16667 10H15.8333M15.8333 10L10 4.16667M15.8333 10L10 15.8333" stroke="currentColor" strokeWidth="1.67" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                </button>
              </div>
            )}

            {/* Generating State */}
            {generating && (
              <div className="flex flex-col gap-4 items-center justify-center w-full py-8">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[#7a0019]"></div>
                <p className="text-slate-800 text-sm">Generating reports... This may take a few minutes.</p>
              </div>
            )}

            {/* Error State */}
            {error && (
              <div className="text-red-600 text-sm text-center">
                {error}
              </div>
            )}
          </div>
        </div>
      </div>
    </main>
  );
}
