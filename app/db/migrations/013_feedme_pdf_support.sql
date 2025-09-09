-- Migration: Add PDF support to FeedMe system
-- Author: PDF Ingestion Implementer
-- Date: 2025-01-09
-- Description: Adds columns for PDF file support including mime type, page count, and metadata

-- Add PDF support columns to feedme_conversations table
ALTER TABLE feedme_conversations
ADD COLUMN IF NOT EXISTS mime_type VARCHAR(50),
ADD COLUMN IF NOT EXISTS pages INTEGER,
ADD COLUMN IF NOT EXISTS pdf_metadata JSONB;

-- Create index for mime type queries to improve performance
CREATE INDEX IF NOT EXISTS idx_feedme_conversations_mime_type 
ON feedme_conversations(mime_type);

-- Add source tracking to feedme_examples table for page references
ALTER TABLE feedme_examples
ADD COLUMN IF NOT EXISTS source_page INTEGER,
ADD COLUMN IF NOT EXISTS source_format VARCHAR(10) DEFAULT 'text';

-- Add comment to document the purpose of new columns
COMMENT ON COLUMN feedme_conversations.mime_type IS 'MIME type of the uploaded file (e.g., application/pdf, text/html)';
COMMENT ON COLUMN feedme_conversations.pages IS 'Number of pages in PDF documents, NULL for other formats';
COMMENT ON COLUMN feedme_conversations.pdf_metadata IS 'Additional PDF metadata (author, creation date, title, etc.)';
COMMENT ON COLUMN feedme_examples.source_page IS 'Page number where this Q&A was extracted from (for PDFs)';
COMMENT ON COLUMN feedme_examples.source_format IS 'Format of source document (pdf, html, text)';