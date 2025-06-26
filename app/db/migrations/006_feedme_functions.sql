-- FeedMe v2.0 Phase 1: Functions and Triggers
-- Create functions and triggers for FeedMe tables

-- Function to automatically update updated_at timestamp
CREATE OR REPLACE FUNCTION update_feedme_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Function to increment version on content changes
CREATE OR REPLACE FUNCTION increment_feedme_version()
RETURNS TRIGGER AS $$
BEGIN
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
$$ language 'plpgsql';

-- Function to update retrieval weight based on feedback
CREATE OR REPLACE FUNCTION update_retrieval_weight()
RETURNS TRIGGER AS $$
DECLARE
    total_feedback INTEGER;
    positive_ratio FLOAT;
BEGIN
    -- Calculate new retrieval weight based on feedback
    total_feedback = NEW.positive_feedback + NEW.negative_feedback;
    
    IF total_feedback > 0 THEN
        positive_ratio = NEW.positive_feedback::FLOAT / total_feedback;
        -- Weight ranges from 0.1 (all negative) to 2.0 (all positive)
        NEW.retrieval_weight = 0.1 + (positive_ratio * 1.9);
    END IF;
    
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create triggers for automatic updates
CREATE TRIGGER trigger_feedme_conversations_updated_at
    BEFORE UPDATE ON feedme_conversations
    FOR EACH ROW
    EXECUTE FUNCTION update_feedme_updated_at();

CREATE TRIGGER trigger_feedme_examples_updated_at
    BEFORE UPDATE ON feedme_examples
    FOR EACH ROW
    EXECUTE FUNCTION increment_feedme_version();

CREATE TRIGGER trigger_feedme_examples_retrieval_weight
    BEFORE UPDATE ON feedme_examples
    FOR EACH ROW
    WHEN (OLD.positive_feedback IS DISTINCT FROM NEW.positive_feedback 
          OR OLD.negative_feedback IS DISTINCT FROM NEW.negative_feedback)
    EXECUTE FUNCTION update_retrieval_weight();