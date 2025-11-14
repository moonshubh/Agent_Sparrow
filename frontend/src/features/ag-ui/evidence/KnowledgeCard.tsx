/**
 * Knowledge Base Card Component
 * Specialized evidence card for KB search results with article metadata
 */

import React from 'react';
import { BookOpen, Tag, Calendar, User } from 'lucide-react';
import { ToolEvidenceCard, ToolEvidenceProps } from './ToolEvidenceCard';

export interface KnowledgeCardProps extends Omit<ToolEvidenceProps, 'type'> {
  articleId?: string;
  category?: string;
  tags?: string[];
  author?: string;
  lastUpdated?: string;
  viewCount?: number;
}

export const KnowledgeCard: React.FC<KnowledgeCardProps> = ({
  articleId,
  category,
  tags = [],
  author,
  lastUpdated,
  viewCount,
  ...props
}) => {
  // Enhanced metadata for knowledge articles
  const enhancedMetadata = {
    ...props.metadata,
    ...(articleId && { 'Article ID': articleId }),
    ...(category && { Category: category }),
    ...(tags.length > 0 && { Tags: tags.join(', ') }),
    ...(author && { Author: author }),
    ...(lastUpdated && { 'Last Updated': lastUpdated }),
    ...(viewCount !== undefined && { Views: viewCount })
  };

  // Format the source to include category if available
  const formattedSource = category
    ? `${props.source || 'Knowledge Base'} / ${category}`
    : props.source || 'Knowledge Base';

  return (
    <ToolEvidenceCard
      {...props}
      type="knowledge"
      source={formattedSource}
      metadata={enhancedMetadata}
      icon={<BookOpen className="w-5 h-5" />}
      className="knowledge-card"
    />
  );
};

// Specialized component for KB article preview
export const KnowledgeArticlePreview: React.FC<{
  articles: KnowledgeCardProps[];
  maxVisible?: number;
}> = ({ articles, maxVisible = 3 }) => {
  const visibleArticles = articles.slice(0, maxVisible);
  const hiddenCount = articles.length - maxVisible;

  return (
    <div className="knowledge-article-preview">
      {visibleArticles.map((article, index) => (
        <KnowledgeCard key={article.articleId || index} {...article} />
      ))}
      {hiddenCount > 0 && (
        <div className="hidden-articles-indicator">
          <span className="hidden-count">+{hiddenCount} more articles</span>
        </div>
      )}
    </div>
  );
};