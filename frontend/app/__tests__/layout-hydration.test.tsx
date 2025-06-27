/**
 * Regression tests for layout hydration fixes
 * Ensures no hydration mismatches occur due to theme or browser extensions
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render } from '@testing-library/react'
import RootLayout from '../layout'

// Mock next/headers cookies
vi.mock('next/headers', () => ({
  cookies: () => ({
    get: vi.fn((name: string) => {
      if (name === 'theme') {
        return { value: 'dark' }
      }
      return undefined
    })
  })
}))

// Mock next/script since it's SSR specific
vi.mock('next/script', () => ({
  default: ({ children, dangerouslySetInnerHTML, ...props }: any) => (
    <script {...props} dangerouslySetInnerHTML={dangerouslySetInnerHTML}>
      {children}
    </script>
  )
}))

// Mock next-themes
vi.mock('next-themes', () => ({
  ThemeProvider: ({ children, defaultTheme, ...props }: any) => (
    <div data-testid="theme-provider" data-default-theme={defaultTheme} {...props}>
      {children}
    </div>
  )
}))

// Mock sonner
vi.mock('@/components/ui/sonner', () => ({
  Toaster: () => <div data-testid="toaster" />
}))

describe('Layout Hydration', () => {
  let consoleWarn: ReturnType<typeof vi.spyOn>;
  let consoleError: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    consoleWarn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    consoleWarn.mockRestore();
    consoleError.mockRestore();
  });

  it('should render without hydration warnings', () => {
    render(
      <RootLayout>
        <div>Test content</div>
      </RootLayout>
    );

    // Check that no hydration warnings were logged
    expect(consoleWarn).not.toHaveBeenCalledWith(
      expect.stringMatching(/hydration|mismatch/i)
    );
    expect(consoleError).not.toHaveBeenCalledWith(
      expect.stringMatching(/hydration|mismatch/i)
    );
  });

  it('should read theme from cookies deterministically', () => {
    // Test that layout properly reads theme from cookies
    // This ensures hydration consistency between server and client
    const { getByTestId } = render(
      <RootLayout>
        <div>Test content</div>
      </RootLayout>
    );

    const themeProvider = getByTestId('theme-provider');
    expect(themeProvider).toHaveAttribute('data-default-theme', 'dark');
  });

  it('should include hydration safety measures', () => {
    // Test that components that could cause hydration issues are handled
    const { container } = render(
      <RootLayout>
        <div>Test content</div>
      </RootLayout>
    );

    // Check that the layout rendered without errors
    expect(container.firstChild).toBeDefined();
    expect(container.querySelector('[data-testid="theme-provider"]')).toBeInTheDocument();
  });

  it('should include Grammarly disable script', () => {
    const { container } = render(
      <RootLayout>
        <div>Test content</div>
      </RootLayout>
    )

    const scripts = container.querySelectorAll('script')
    const grammarlyScript = Array.from(scripts).find(script => 
      script.id === 'disable-grammarly'
    )

    expect(grammarlyScript).toBeDefined()
    expect(grammarlyScript?.getAttribute('strategy')).toBe('beforeInteractive')
  })
})