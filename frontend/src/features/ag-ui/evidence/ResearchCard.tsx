/**
 * Research Card Component
 * Specialized evidence card for web search results with domain grouping
 */

import React, { useMemo } from 'react';
import { Globe, Search, LinkIcon, AlertCircle, Zap } from 'lucide-react';
import { ToolEvidenceCard, ToolEvidenceProps } from './ToolEvidenceCard';
import { motion } from 'framer-motion';

export interface ResearchResult {
  url: string;
  title: string;
  snippet: string;
  domain?: string;
  searchService?: 'gemini_grounding' | 'tavily' | 'firecrawl';
  extractionSuccess?: boolean;
}

export interface ResearchCardProps extends Omit<ToolEvidenceProps, 'type' | 'url'> {
  results: ResearchResult[];
  searchQuery?: string;
  searchService?: string;
  fallbackChain?: string[];
  totalResults?: number;
}

export const ResearchCard: React.FC<ResearchCardProps> = ({
  results,
  searchQuery,
  searchService,
  fallbackChain,
  totalResults,
  ...props
}) => {
  // Group results by domain
  const groupedResults = useMemo(() => {
    const groups: Record<string, ResearchResult[]> = {};
    results.forEach(result => {
      let domain: string;
      try {
        domain = result.domain || new URL(result.url).hostname;
      } catch (error) {
        // Fallback to result.domain or URL string if URL parsing fails
        domain = result.domain || result.url;
        console.warn(`Failed to parse URL hostname for ${result.url}:`, error);
      }
      if (!groups[domain]) {
        groups[domain] = [];
      }
      groups[domain].push(result);
    });
    return groups;
  }, [results]);

  // Format full content from all results
  const fullContent = results
    .map((result, index) =>
      `[${index + 1}] ${result.title}\n${result.url}\n${result.snippet}\n`
    )
    .join('\n');

  // Create a summary snippet
  const snippet = results.length > 0
    ? `Found ${results.length} results from ${Object.keys(groupedResults).length} domains`
    : 'No results found';

  // Enhanced metadata
  const enhancedMetadata = {
    ...props.metadata,
    ...(searchQuery && { 'Search Query': searchQuery }),
    ...(searchService && { 'Search Service': searchService }),
    ...(fallbackChain && fallbackChain.length > 0 && {
      'Service Chain': fallbackChain.join(' → ')
    }),
    ...(totalResults && { 'Total Results': totalResults })
  };

  // Determine status based on service and results
  const status = fallbackChain && fallbackChain.length > 1
    ? 'fallback'
    : results.length === 0
    ? 'partial'
    : 'success';

  const fallbackReason = fallbackChain && fallbackChain.length > 1
    ? `Used ${fallbackChain[fallbackChain.length - 1]} after ${fallbackChain[0]} failed`
    : undefined;

  return (
    <div className="research-card-container">
      <ToolEvidenceCard
        {...props}
        type="research"
        title={props.title || `Web Search Results`}
        source={searchService || 'Web Search'}
        snippet={snippet}
        fullContent={fullContent}
        metadata={enhancedMetadata}
        status={status}
        fallbackReason={fallbackReason}
        icon={<Globe className="w-5 h-5" />}
        className="research-card"
      />

      {/* Domain grouped results preview */}
      {results.length > 0 && (
        <motion.div
          className="research-results-preview"
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3, delay: 0.1 }}
        >
          {Object.entries(groupedResults).slice(0, 3).map(([domain, domainResults]) => (
            <DomainGroup
              key={domain}
              domain={domain}
              results={domainResults}
              searchService={searchService}
            />
          ))}
        </motion.div>
      )}
    </div>
  );
};

// Domain group component
const DomainGroup: React.FC<{
  domain: string;
  results: ResearchResult[];
  searchService?: string;
}> = ({ domain, results, searchService }) => {
  const getServiceIcon = (service?: string) => {
    switch (service) {
      case 'gemini_grounding':
        return <Zap className="w-3 h-3" />;
      case 'tavily':
        return <Search className="w-3 h-3" />;
      case 'firecrawl':
        return <LinkIcon className="w-3 h-3" />;
      default:
        return <Globe className="w-3 h-3" />;
    }
  };

  return (
    <motion.div
      className="domain-group glass-panel"
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.2 }}
      whileHover={{ scale: 1.02 }}
    >
      <div className="domain-header">
        <div className="domain-info">
          {getServiceIcon(searchService)}
          <span className="domain-name">{domain}</span>
          <span className="result-count">{results.length} result{results.length > 1 ? 's' : ''}</span>
        </div>
      </div>
      <div className="domain-results">
        {results.slice(0, 2).map((result, index) => (
          <a
            key={index}
            href={result.url}
            target="_blank"
            rel="noopener noreferrer"
            className="result-link"
            onClick={(e) => e.stopPropagation()}
          >
            <h5 className="result-title">{result.title}</h5>
            <p className="result-snippet">{result.snippet}</p>
          </a>
        ))}
      </div>
    </motion.div>
  );
};

// Enhanced styles for research cards
const researchCardStyles = `
  .research-card-container {
    position: relative;
  }

  .research-results-preview {
    margin-top: var(--space-md);
    display: flex;
    flex-direction: column;
    gap: var(--space-sm);
  }

  .domain-group {
    padding: var(--space-md);
    background: hsla(228, 62%, 10%, 0.4);
    border: 1px solid hsla(45, 100%, 50%, 0.2);
    border-radius: var(--radius-md);
    transition: all var(--duration-fast) var(--ease-smooth);
  }

  .domain-group:hover {
    border-color: hsla(45, 100%, 50%, 0.4);
    box-shadow: 0 0 15px hsla(45, 100%, 50%, 0.1);
  }

  .domain-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: var(--space-sm);
  }

  .domain-info {
    display: flex;
    align-items: center;
    gap: var(--space-xs);
    color: var(--accent-amber-400);
  }

  .domain-name {
    font-weight: var(--font-weight-semibold);
    font-family: var(--font-family-mono);
  }

  .result-count {
    color: var(--neutral-500);
    font-size: var(--font-size-sm);
  }

  .domain-results {
    display: flex;
    flex-direction: column;
    gap: var(--space-xs);
  }

  .result-link {
    display: block;
    padding: var(--space-xs);
    border-radius: var(--radius-sm);
    text-decoration: none;
    transition: all var(--duration-fast) var(--ease-smooth);
  }

  .result-link:hover {
    background: hsla(45, 100%, 50%, 0.05);
  }

  .result-title {
    color: var(--crystal-cyan-300);
    font-size: var(--font-size-sm);
    font-weight: var(--font-weight-medium);
    margin: 0 0 var(--space-xs) 0;
    line-height: var(--line-height-tight);
  }

  .result-snippet {
    color: var(--neutral-400);
    font-size: var(--font-size-xs);
    line-height: var(--line-height-normal);
    margin: 0;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }
`;

// Inject styles (with deduplication check)
if (typeof document !== 'undefined' && !document.getElementById('research-card-styles')) {
  const style = document.createElement('style');
  style.id = 'research-card-styles';
  style.textContent = researchCardStyles;
  document.head.appendChild(style);
}