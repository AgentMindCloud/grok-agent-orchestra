import "./globals.css";

import type { Metadata, Viewport } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import type { ReactNode } from "react";

import { Header } from "@/components/header";
import { ThemeProvider } from "@/components/theme-provider";
import { cn } from "@/lib/utils";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter", display: "swap" });
const mono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  display: "swap",
});

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? "https://agent-orchestra.local";
const SITE_NAME = process.env.NEXT_PUBLIC_SITE_NAME ?? "Agent Orchestra";
const TAGLINE =
  "Multi-agent research with visible debate and enforceable safety vetoes — powered by Grok.";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: {
    default: SITE_NAME,
    template: `%s · ${SITE_NAME}`,
  },
  description: TAGLINE,
  applicationName: SITE_NAME,
  keywords: [
    "multi-agent",
    "Grok",
    "LLM orchestration",
    "AI safety",
    "deep research",
    "agentic AI",
  ],
  authors: [{ name: "AgentMindCloud" }],
  openGraph: {
    type: "website",
    siteName: SITE_NAME,
    title: SITE_NAME,
    description: TAGLINE,
    url: SITE_URL,
    images: [{ url: "/opengraph-image", width: 1200, height: 630, alt: SITE_NAME }],
  },
  twitter: {
    card: "summary_large_image",
    title: SITE_NAME,
    description: TAGLINE,
  },
  icons: {
    icon: "/favicon.ico",
  },
  robots: {
    index: true,
    follow: true,
  },
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#ff6b35" },
    { media: "(prefers-color-scheme: dark)", color: "#0d0d0d" },
  ],
  width: "device-width",
  initialScale: 1,
};

const JSON_LD = {
  "@context": "https://schema.org",
  "@type": "SoftwareApplication",
  name: SITE_NAME,
  description: TAGLINE,
  applicationCategory: "DeveloperApplication",
  operatingSystem: "macOS, Linux, Windows",
  offers: { "@type": "Offer", price: "0", priceCurrency: "USD" },
  url: SITE_URL,
  author: { "@type": "Organization", name: "AgentMindCloud" },
  license: "https://www.apache.org/licenses/LICENSE-2.0",
};

export default function RootLayout({
  children,
}: Readonly<{ children: ReactNode }>): JSX.Element {
  return (
    <html lang="en" suppressHydrationWarning>
      <body
        className={cn(
          inter.variable,
          mono.variable,
          "min-h-screen bg-background font-sans text-foreground",
        )}
      >
        <ThemeProvider
          attribute="class"
          defaultTheme="dark"
          enableSystem
          disableTransitionOnChange
        >
          <div className="flex min-h-screen flex-col">
            <Header />
            <main className="container flex-1 py-8">{children}</main>
            <footer className="border-t border-border/60 py-6 text-center text-xs text-muted-foreground">
              <p>
                Lucas vetoes everything before it ships. ·{" "}
                <a
                  href="/classic/"
                  className="underline-offset-4 hover:underline"
                >
                  Classic dashboard
                </a>
              </p>
            </footer>
          </div>
        </ThemeProvider>
        <script
          type="application/ld+json"
          // SoftwareApplication schema improves SERP rich-result eligibility.
          dangerouslySetInnerHTML={{ __html: JSON.stringify(JSON_LD) }}
        />
      </body>
    </html>
  );
}
