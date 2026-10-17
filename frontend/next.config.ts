import type { NextConfig } from "next";

const staticExport = process.env.NEXT_OUTPUT === "export";

const nextConfig: NextConfig = {
  // Docker builds: "standalone" (own Node server) or "export" (static files served by the API,
  // see the root Dockerfile). Vercel builds set neither.
  output: process.env.NEXT_OUTPUT === "standalone" || process.env.NEXT_OUTPUT === "export"
    ? process.env.NEXT_OUTPUT : undefined,
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
