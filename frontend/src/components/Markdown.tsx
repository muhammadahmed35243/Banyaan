"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

/** Agent answers are Markdown: headings, bullets, tables, links and images from the web. */
export default function Markdown({ text }: { text: string }) {
  return (
    <div className="banyan-md text-sm leading-relaxed text-slate-200">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ href, children }) => (
            <a href={href} target="_blank" rel="noreferrer noopener" className="text-sky-400 underline hover:text-sky-300">{children}</a>
          ),
          img: ({ src, alt }) => (
            // Remote images from any site: next/image would need every domain allow-listed.
            // eslint-disable-next-line @next/next/no-img-element
            <img src={typeof src === "string" ? src : undefined} alt={alt ?? ""} loading="lazy" referrerPolicy="no-referrer"
              className="my-2 mr-2 inline-block h-32 rounded-lg border border-slate-700 object-cover"
              onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = "none"; }} />
          ),
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
}
