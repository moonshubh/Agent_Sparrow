-- Migration: Fix Supabase search_path security warnings
-- This migration recreates functions with immutable search_path to fix security warnings

-- 1. Fix update_feedme_updated_at function with secure search_path
CREATE OR REPLACE FUNCTION update_feedme_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    SET search_path = '';
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql' SECURITY DEFINER;

-- 2. Fix update_retrieval_weight function with secure search_path  
CREATE OR REPLACE FUNCTION update_retrieval_weight()
RETURNS TRIGGER AS $$
DECLARE
    total_feedback INTEGER;
    positive_ratio FLOAT;
BEGIN
    SET search_path = '';
    
    -- Calculate new retrieval weight based on feedback
    total_feedback = NEW.positive_feedback + NEW.negative_feedback;
    
    IF total_feedback > 0 THEN
        positive_ratio = NEW.positive_feedback::FLOAT / total_feedback;
        -- Weight ranges from 0.1 (all negative) to 2.0 (all positive)
        NEW.retrieval_weight = 0.1 + (positive_ratio * 1.9);
    END IF;
    
    RETURN NEW;
END;
$$ language 'plpgsql' SECURITY DEFINER;

-- 3. Fix increment_feedme_version function with secure search_path
CREATE OR REPLACE FUNCTION increment_feedme_version()
RETURNS TRIGGER AS $$
BEGIN
    SET search_path = '';
    
    -- Increment version for any content changes
    IF OLD.question_text IS DISTINCT FROM NEW.question_text 
       OR OLD.answer_text IS DISTINCT FROM NEW.answer_text 
       OR OLD.tags IS DISTINCT FROM NEW.tags
       OR OLD.issue_type IS DISTINCT FROM NEW.issue_type
       OR OLD.resolution_type IS DISTINCT FROM NEW.resolution_type THEN
        NEW.version = OLD.version + 1;
    END IF;
    
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql' SECURITY DEFINER;

-- 4. Create a generic timestamp trigger function (if trigger_set_timestamp was referenced elsewhere)
CREATE OR REPLACE FUNCTION trigger_set_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    SET search_path = '';
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql' SECURITY DEFINER;

-- Add comments for clarity
COMMENT ON FUNCTION update_feedme_updated_at() IS 'Securely updates updated_at timestamp with immutable search_path';
COMMENT ON FUNCTION update_retrieval_weight() IS 'Securely calculates retrieval weight based on feedback with immutable search_path';  
COMMENT ON FUNCTION increment_feedme_version() IS 'Securely increments version on content changes with immutable search_path';
COMMENT ON FUNCTION trigger_set_timestamp() IS 'Generic secure timestamp trigger function with immutable search_path';