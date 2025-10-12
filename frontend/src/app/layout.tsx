import type { Metadata } from "next";
import Script from "next/script";
import { ThemeProvider } from "next-themes";
import { cookies } from "next/headers";
import "./globals.css";
import { Toaster } from "@/shared/ui/sonner";
import { AuthProvider } from "@/shared/contexts/AuthContext";
import { ChunkErrorRecovery } from "@/shared/components/utils/ChunkErrorRecovery";

export const metadata: Metadata = {
  title: 'MB-Sparrow Agent',
  description: 'Multi-agent AI system for Mailbird customer support',
  generator: 'MB-Sparrow',
}

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  // Read theme from cookies on server side for consistent SSR/CSR
  const cookieStore = await cookies();
  const themeCookie = cookieStore.get('theme');
  const initialTheme = themeCookie?.value || 'dark'; // Default to dark per design direction

  return (
    <html lang="en" data-theme={initialTheme} suppressHydrationWarning>
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
          defaultTheme={initialTheme}
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
