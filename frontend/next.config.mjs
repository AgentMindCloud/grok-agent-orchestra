/** @type {import('next').NextConfig} */
const baseConfig = {
  reactStrictMode: true,
  // Static export so the FastAPI backend can serve the built UI from
  // a single port in production. `out/` is what the Dockerfile copies
  // into the runtime image.
  output: process.env.NEXT_BUILD_TARGET === "export" ? "export" : undefined,
  trailingSlash: true,
  images: { unoptimized: true },
  poweredByHeader: false,
  experimental: {
    typedRoutes: false,
  },
  // Custom webpack tweaks:
  // - Tree-shake Radix harder by ensuring side-effect-free re-exports.
  webpack: (config) => {
    config.resolve.fallback = { ...(config.resolve.fallback ?? {}), fs: false };
    return config;
  },
};

// Optional bundle analyser. Activated with `ANALYZE=true pnpm build` —
// installs lazily so users without the dev dep don't fail the build.
async function withOptionalAnalyzer(config) {
  if (process.env.ANALYZE !== "true") return config;
  try {
    const { default: bundleAnalyzer } = await import("@next/bundle-analyzer");
    return bundleAnalyzer({ enabled: true })(config);
  } catch {
    // Fail open — analyzer is dev-only.
    return config;
  }
}

export default await withOptionalAnalyzer(baseConfig);
