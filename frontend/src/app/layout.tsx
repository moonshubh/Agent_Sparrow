import type { Metadata } from "next";
import Script from "next/script";
import { ThemeProvider } from "next-themes";
// no server-side cookies read here; keep layout minimal
import "./globals.css";
import { Toaster } from "@/shared/ui/sonner";
import { AuthProvider } from "@/shared/contexts/AuthContext";
import { ChunkErrorRecovery } from "@/shared/components/utils/ChunkErrorRecovery";

export const metadata: Metadata = {
  title: 'MB-Sparrow Agent',
  description: 'Multi-agent AI system for Mailbird customer support',
  generator: 'MB-Sparrow',
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        {/* Dark Academia Typography - Lora (primary serif) + Poppins (UI fallback) */}
        <link
          rel="stylesheet"
          href="https://fonts.googleapis.com/css2?family=Lora:ital,wght@0,400;0,500;0,600;0,700;1,400;1,500&family=Poppins:wght@400;500;600&display=swap"
        />
        <link
          rel="stylesheet"
          href="https://cdn.jsdelivr.net/npm/katex@0.16.25/dist/katex.min.css"
          crossOrigin="anonymous"
        />
      </head>
      <body className="antialiased" suppressHydrationWarning>
        <Script 
          id="disable-grammarly" 
          strategy="beforeInteractive"
          dangerouslySetInnerHTML={{
            __html: `
              if (typeof window !== 'undefined') {
                Object.defineProperty(window, 'Grammarly', { value: null, writable: false });
                Object.defineProperty(window, '__grammarly', { value: null, writable: false });
              }
            `
          }}
        />
        <ThemeProvider
          attribute="class"
          defaultTheme="dark"
          enableSystem
          disableTransitionOnChange
        >
          <AuthProvider>
            <ChunkErrorRecovery />
            {children}
          </AuthProvider>
          <Toaster />
        </ThemeProvider>
      </body>
    </html>
  )
}
