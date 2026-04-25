/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Static export so the FastAPI backend can serve the built UI from
  // a single port in production. `out/` is what the Dockerfile copies
  // into the runtime image.
  output: process.env.NEXT_BUILD_TARGET === "export" ? "export" : undefined,
  trailingSlash: true,
  images: { unoptimized: true },
  experimental: {
    typedRoutes: false,
  },
};

export default nextConfig;
