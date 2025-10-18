import { FileUploadCard } from "./FileUploadCard";

export function UploadSection() {
  return (
    <div className="box-border flex flex-1 flex-col gap-10 items-center min-h-px min-w-px px-16 py-[120px] relative shrink-0 w-full">
      <div className="flex flex-col gap-2 items-center justify-end relative shrink-0 text-center w-full">
        <div className="font-semibold relative shrink-0 text-2xl text-slate-950 whitespace-nowrap">
          Upload Invention Disclosure
        </div>
        <div className="font-normal relative shrink-0 text-base text-slate-800 w-[400px]">
          Use AI to analyze invention disclosures for novelty and
          commercialization potential.
        </div>
      </div>
      <FileUploadCard />
    </div>
  );
}
