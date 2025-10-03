interface KeyFindingsProps {
  findings: string[];
}

export function KeyFindings({ findings }: KeyFindingsProps) {
  return (
    <div className="border border-slate-100 box-border flex flex-col gap-4 items-end justify-end p-4 rounded-2xl w-full">
      <div className="flex flex-col gap-2 items-start w-full">
        <div className="flex gap-2 items-start w-full">
          <div className="flex flex-1 gap-2 items-center">
            <div className="font-semibold text-base text-slate-950 whitespace-nowrap">
              Key Findings
            </div>
          </div>
        </div>
        <div className="flex flex-col font-normal gap-2 items-start text-base text-slate-800 w-full">
          {findings.map((finding, index) => (
            <div key={index} className="w-full">
              <ul>
                <li className="list-disc ms-6 whitespace-pre-wrap">
                  <span className="leading-6">{finding}</span>
                </li>
              </ul>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
