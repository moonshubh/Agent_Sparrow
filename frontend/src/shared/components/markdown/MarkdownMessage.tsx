import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface MarkdownMessageProps {
  content: string;
}

export const MarkdownMessage = ({ content }: MarkdownMessageProps) => (
  <div
    className="prose prose-sm max-w-none dark:prose-invert
                  prose-headings:font-semibold prose-headings:text-foreground prose-headings:mb-3 prose-headings:mt-4
                  prose-h2:text-base
                  prose-ul:my-2 prose-ol:my-2 prose-li:my-1
                  prose-p:mb-3 prose-p:leading-relaxed prose-p:text-foreground
                  prose-strong:text-foreground prose-strong:font-semibold
                  prose-code:bg-muted/60 prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded prose-code:text-sm
                  prose-pre:bg-muted/60 prose-pre:rounded-lg prose-pre:px-4 prose-pre:py-3 prose-pre:border prose-pre:border-border/40
                  prose-blockquote:border-l-accent prose-blockquote:bg-accent/5 prose-blockquote:pl-4 prose-blockquote:italic
                  prose-a:text-accent prose-a:underline prose-a:decoration-accent/50
                  [&>*:first-child]:mt-0 [&>*:last-child]:mb-0"
  >
    <ReactMarkdown remarkPlugins={[remarkGfm]}>{content.trim()}</ReactMarkdown>
  </div>
);
