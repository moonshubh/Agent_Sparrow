import type { Metadata } from 'next';
import Script from 'next/script';
import { ThemeProvider } from 'next-themes';
import { Lora, Poppins } from 'next/font/google';
// no server-side cookies read here; keep layout minimal
import './globals.css';
import { Toaster } from '@/shared/ui/sonner';
import { AuthProvider } from '@/shared/contexts/AuthContext';
import { ChunkErrorRecovery } from '@/shared/components/utils/ChunkErrorRecovery';

const lora = Lora({
  subsets: ['latin'],
  variable: '--font-lora',
  display: 'swap',
  weight: ['400', '500', '600', '700'],
  style: ['normal', 'italic'],
});

const poppins = Poppins({
  subsets: ['latin'],
  variable: '--font-poppins',
  display: 'swap',
  weight: ['400', '500', '600'],
});

export const metadata: Metadata = {
  title: 'MB-Sparrow Agent',
  description: 'Multi-agent AI system for Mailbird customer support',
  generator: 'MB-Sparrow',
  icons: {
    icon: [
      { url: '/Sparrow_logo.png', sizes: '32x32', type: 'image/png' },
      { url: '/Sparrow_logo.png', sizes: '16x16', type: 'image/png' },
      { url: '/Sparrow_logo.png', sizes: '192x192', type: 'image/png' },
      { url: '/Sparrow_logo.png', sizes: '512x512', type: 'image/png' },
    ],
    apple: [
      { url: '/Sparrow_logo.png', sizes: '180x180', type: 'image/png' },
    ],
    shortcut: ['/Sparrow_logo.png'],
  },
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <link rel="icon" href="/Sparrow_logo.png" type="image/png" sizes="32x32" />
        <link rel="shortcut icon" href="/Sparrow_logo.png" />
        <link rel="apple-touch-icon" href="/Sparrow_logo.png" />
        <link
          rel="stylesheet"
          href="https://cdn.jsdelivr.net/npm/katex@0.16.25/dist/katex.min.css"
          crossOrigin="anonymous"
        />
      </head>
      <body className={`${lora.variable} ${poppins.variable} antialiased`} suppressHydrationWarning>
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
