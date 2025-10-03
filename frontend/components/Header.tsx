import Image from "next/image";

export function Header() {
  return (
    <div className="box-border flex items-center justify-between px-16 py-6 relative shrink-0 w-full border-b border-slate-100">
      <div className="flex flex-1 items-center">
        <div className="flex flex-1 h-full items-center justify-between min-h-px min-w-px relative">
          <div className="h-9 relative shrink-0 w-[133.2px]">
            <Image
              src="/University_of_Minnesota_wordmark.png"
              alt="University of Minnesota"
              width={133}
              height={36}
              className="object-contain"
              priority
            />
          </div>
          <div 
            className="absolute font-semibold text-lg text-center text-slate-950 top-[11px] whitespace-nowrap"
            style={{ left: "calc(50% + 0.5px)", transform: "translateX(-50%)" }}
          >
            Patent Search Tool
          </div>
        </div>
      </div>
    </div>
  );
}
