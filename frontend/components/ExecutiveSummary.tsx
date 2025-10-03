interface ExecutiveSummaryProps {
  summary: string;
}

export function ExecutiveSummary({ summary }: ExecutiveSummaryProps) {
  return (
    <div className="border border-slate-100 box-border flex flex-col items-end justify-end p-4 rounded-2xl w-full">
      <div className="flex flex-col gap-2 items-start w-full">
        <div className="flex gap-2 items-start w-full">
          <div className="flex flex-1 gap-2 items-center">
            <div className="font-semibold text-base text-slate-950 whitespace-nowrap">
              Executive Summary
            </div>
          </div>
        </div>
        <div className="font-normal text-base text-slate-800 w-full">
          <p className="leading-6 whitespace-pre-wrap">{summary}</p>
        </div>
      </div>
    </div>
  );
}
