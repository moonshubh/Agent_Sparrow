import type { Metadata } from "next";
import { ThemeProvider } from "next-themes";
import { cookies } from "next/headers";
import "./globals.css";
import { Toaster } from "@/components/ui/sonner";

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
  // Read theme from cookies on server side for consistent SSR/CSR
  const cookieStore = cookies();
  const themeCookie = cookieStore.get('theme');
  const initialTheme = themeCookie?.value || 'light'; // Default to light for consistency

  return (
    <html lang="en" data-theme={initialTheme} suppressHydrationWarning>
      <body className="antialiased">
        <ThemeProvider
          attribute="class"
          defaultTheme={initialTheme}
          enableSystem
          disableTransitionOnChange
        >
          {children}
          <Toaster />
        </ThemeProvider>
      </body>
    </html>
  )
}
