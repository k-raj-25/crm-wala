"use client";
import Link from "next/link";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { cn } from "@crm/ui";

export function Markdown({ children, className }: { children: string; className?: string }) {
  return (
    <div className={cn("text-sm leading-relaxed [&>*+*]:mt-3", className)}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={{
        a: ({ href = "", children }) => href.startsWith("/") ? <Link href={href} className="font-medium text-primary hover:underline">{children}</Link> : <a href={href} target="_blank" rel="noreferrer noopener" className="font-medium text-primary hover:underline">{children}</a>,
        ul: (p) => <ul className="list-disc space-y-1 pl-5" {...p} />, ol: (p) => <ol className="list-decimal space-y-1 pl-5" {...p} />,
        strong: (p) => <strong className="font-semibold text-fg" {...p} />, h1: (p) => <h3 className="text-base font-semibold" {...p} />, h2: (p) => <h3 className="text-base font-semibold" {...p} />, h3: (p) => <h4 className="font-semibold" {...p} />,
        code: ({ className, children }) => className ? <code className="block whitespace-pre-wrap rounded-lg bg-bg-subtle p-3 font-sans text-[13px]">{children}</code> : <code className="rounded bg-bg-subtle px-1 py-0.5 text-[13px]">{children}</code>,
        pre: ({ children }) => <>{children}</>,
        table: (p) => <div className="overflow-x-auto"><table className="w-full text-[13px]" {...p} /></div>, th: (p) => <th className="border-b border-border px-3 py-2 text-left text-xs font-medium text-fg-subtle" {...p} />, td: (p) => <td className="border-b border-border px-3 py-2" {...p} />,
      }}>{children}</ReactMarkdown>
    </div>
  );
}
