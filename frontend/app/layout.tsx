import "./globals.css";

import type { Metadata } from "next";
import type { ReactNode } from "react";
import { Inter, JetBrains_Mono } from "next/font/google";

import { Header } from "@/components/header";
import { ThemeProvider } from "@/components/theme-provider";
import { cn } from "@/lib/utils";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });
const mono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
});

export const metadata: Metadata = {
  title: "Agent Orchestra",
  description:
    "Multi-agent research with visible debate and enforceable safety vetoes — powered by Grok.",
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
      </body>
    </html>
  );
}
