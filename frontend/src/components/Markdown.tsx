"use client";

import ReactMarkdown from "react-markdown";
import rehypeKatex from "rehype-katex";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import "katex/dist/katex.min.css";

/** Models sometimes write $$...$$ (or a stray $$...$) mid-sentence. Display math only works on
 * its own line, so inside running text turn it into inline math. */
function fixMath(text: string): string {
  return text.split("\n").map((line) => {
    const t = line.trim();
    if (!t.includes("$$") || /^\$\$.*\$\$$/.test(t) || t === "$$") return line;
    return line.replace(/\$\$/g, "$");
  }).join("\n");
}

/** Agent answers are Markdown: headings, bullets, tables, links, images from the web, and math
 * ($x^2$ inline, $$...$$ display) rendered with KaTeX, e.g. matrices in a solved assignment. */
export default function Markdown({ text }: { text: string }) {
  return (
    <div className="banyan-md text-sm leading-relaxed text-slate-200">
      <ReactMarkdown
        remarkPlugins={[remarkGfm, [remarkMath, { singleDollarTextMath: true }]]}
        rehypePlugins={[[rehypeKatex, { throwOnError: false, strict: "ignore" }]]}
        components={{
          a: ({ href, children }) => (
            <a href={href} target="_blank" rel="noreferrer noopener" className="text-af-medium underline hover:text-af-medium-hover">{children}</a>
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
        {fixMath(text)}
      </ReactMarkdown>
    </div>
  );
}
