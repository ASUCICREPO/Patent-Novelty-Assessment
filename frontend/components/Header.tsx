"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";

export function Header() {
  const pathname = usePathname();
  const isHomePage = pathname === "/";

  return (
    <div className="box-border flex items-center justify-between px-16 py-6 relative shrink-0 w-full border-b border-slate-100">
      <div className="flex flex-1 items-center">
        <div className="flex flex-1 h-full items-center justify-between min-h-px min-w-px relative">
          <Link href="/" className="h-9 relative shrink-0 w-[133.2px] cursor-pointer hover:opacity-80 transition-opacity">
            <Image
              src="/University_of_Minnesota_wordmark.png"
              alt="University of Minnesota"
              fill
              sizes="133px"
              className="object-contain"
              priority
            />
          </Link>
          <div 
            className="absolute font-semibold text-lg text-center text-slate-950 top-[11px] whitespace-nowrap"
            style={{ left: "calc(50% + 0.5px)", transform: "translateX(-50%)" }}
          >
            Patent Search Tool
          </div>
          {!isHomePage && (
            <Link 
              href="/"
              className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-[#7a0019] hover:bg-[#fff7f9] rounded-lg transition-colors"
            >
              <svg 
                width="20" 
                height="20" 
                viewBox="0 0 20 20" 
                fill="none" 
                xmlns="http://www.w3.org/2000/svg"
                className="shrink-0"
              >
                <path 
                  d="M3 10L10 3L17 10M4 9V16C4 16.5523 4.44772 17 5 17H8V13C8 12.4477 8.44772 12 9 12H11C11.5523 12 12 12.4477 12 13V17H15C15.5523 17 16 16.5523 16 16V9" 
                  stroke="currentColor" 
                  strokeWidth="1.5" 
                  strokeLinecap="round" 
                  strokeLinejoin="round"
                />
              </svg>
              Home
            </Link>
          )}
        </div>
      </div>
    </div>
  );
}
