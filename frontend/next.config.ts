import type { NextConfig } from "next";

const output = process.env.NEXT_OUTPUT === "standalone" || process.env.NEXT_OUTPUT === "export"
  ? process.env.NEXT_OUTPUT : undefined;
const staticExport = output === "export";

const nextConfig: NextConfig = {
  // Docker builds: "standalone" (own Node server) or "export" (static files served by the API,
  // see the root Dockerfile). Vercel builds set neither.
  output,
  // Exported pages become <route>/index.html, which the API's static file server finds.
  trailingSlash: staticExport,
  // Partial prerendering can't run in a static export.
  cacheComponents: !staticExport,
  partialPrefetching: !staticExport,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
