"use client";

import { useState, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { updateKeywords } from "@/lib/dynamodb";

interface KeywordsProps {
  keywords: string[];
  fileName: string;
  onKeywordsChange?: (keywords: string[]) => void;
}

export function Keywords({ keywords, fileName, onKeywordsChange }: KeywordsProps) {
  const [searchKeywords, setSearchKeywords] = useState<string[]>(keywords);
  const [newKeyword, setNewKeyword] = useState("");
  const [isUpdating, setIsUpdating] = useState(false);
  const [updateError, setUpdateError] = useState<string | null>(null);

  const updateKeywordsInDB = useCallback(async (updatedKeywords: string[]) => {
    try {
      setIsUpdating(true);
      setUpdateError(null);
      await updateKeywords(fileName, updatedKeywords);
      onKeywordsChange?.(updatedKeywords);
    } catch (error) {
      console.error("Failed to update keywords:", error);
      setUpdateError("Failed to save keywords. Please try again.");
    } finally {
      setIsUpdating(false);
    }
  }, [fileName, onKeywordsChange]);

  const handleRemoveKeyword = async (indexToRemove: number) => {
    const updatedKeywords = searchKeywords.filter((_, index) => index !== indexToRemove);
    setSearchKeywords(updatedKeywords);
    await updateKeywordsInDB(updatedKeywords);
  };

  const handleAddKeyword = async () => {
    if (newKeyword.trim() && !searchKeywords.includes(newKeyword.trim())) {
      const updatedKeywords = [...searchKeywords, newKeyword.trim()];
      setSearchKeywords(updatedKeywords);
      setNewKeyword("");
      await updateKeywordsInDB(updatedKeywords);
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") {
      e.preventDefault();
      handleAddKeyword();
    }
  };

  return (
    <div className="border border-slate-100 box-border flex flex-col items-end justify-end p-4 rounded-2xl w-full">
      <div className="flex flex-col gap-4 items-start w-full">
        {/* Search Keywords Section */}
        <div className="flex flex-col gap-2 items-start w-full">
          <div className="flex gap-2 items-start w-full">
            <div className="flex flex-1 gap-2 items-center">
              <div className="font-semibold text-base text-slate-950 whitespace-nowrap">
                Search Keywords
              </div>
            </div>
          </div>
          <div className="flex flex-wrap gap-2 items-start w-full">
            {searchKeywords.map((keyword, index) => (
              <div
                key={index}
                className="text-slate-700 px-2 py-1 rounded-lg text-sm font-medium flex items-center gap-1.5"
                style={{ backgroundColor: '#F9FAFB', borderColor: '#E2E8F0', borderWidth: '1px', borderStyle: 'solid' }}
              >
                <span>{keyword}</span>
                <button
                  onClick={() => handleRemoveKeyword(index)}
                  disabled={isUpdating}
                  className="text-slate-500 hover:text-slate-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed ml-1"
                  aria-label={`Remove ${keyword}`}
                >
                  <svg
                    width="14"
                    height="14"
                    viewBox="0 0 14 14"
                    fill="none"
                    xmlns="http://www.w3.org/2000/svg"
                  >
                    <path
                      d="M10.5 3.5L3.5 10.5M3.5 3.5L10.5 10.5"
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
          {isUpdating && (
            <div className="text-xs text-slate-600">
              Saving changes...
            </div>
          )}
          {updateError && (
            <div className="text-xs text-red-600">
              {updateError}
            </div>
          )}
        </div>

        {/* Add Keywords Section */}
        <div className="flex flex-col gap-2 items-start w-full">
          <div className="flex gap-2 items-start w-full">
            <div className="flex flex-1 gap-2 items-center">
              <div className="font-semibold text-base text-slate-950 whitespace-nowrap">
                Add Keywords
              </div>
            </div>
          </div>
          <div className="flex gap-2 items-center w-full">
            <input
              type="text"
              value={newKeyword}
              onChange={(e) => setNewKeyword(e.target.value)}
              onKeyPress={handleKeyPress}
              placeholder="Add custom keywords"
              className="flex-1 px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-[#7a0019] focus:border-transparent"
            />
            <Button
              onClick={handleAddKeyword}
              disabled={!newKeyword.trim() || searchKeywords.includes(newKeyword.trim()) || isUpdating}
              className="bg-[#7a0019] hover:bg-[#5d0013] text-white font-medium text-sm px-4 py-2 rounded-lg flex items-center gap-2 disabled:bg-[#7a0019] disabled:cursor-not-allowed"
            >
              {isUpdating ? "Adding..." : "Add Keyword"}
              {!isUpdating && (
                <svg
                  width="16"
                  height="16"
                  viewBox="0 0 16 16"
                  fill="none"
                  xmlns="http://www.w3.org/2000/svg"
                >
                  <path
                    d="M8 3.33334V12.6667M3.33334 8H12.6667"
                    stroke="currentColor"
                    strokeWidth="1.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              )}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
