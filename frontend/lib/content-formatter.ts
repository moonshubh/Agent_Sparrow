/**
 * Content Formatter for FeedMe Q&A Examples
 * 
 * Intelligently formats plain text support responses into structured markdown
 * for better readability and presentation in the frontend.
 */

export interface FormattingOptions {
  preserveOriginal?: boolean
  enhanceInstructions?: boolean
  highlightTechnicalTerms?: boolean
  addLineBreaks?: boolean
}

/**
 * Formats plain text support content into structured markdown
 */
export function formatSupportContent(
  content: string, 
  options: FormattingOptions = {}
): string {
  const {
    preserveOriginal = false,
    enhanceInstructions = true,
    highlightTechnicalTerms = true,
    addLineBreaks = true
  } = options

  if (!content?.trim()) return content

  let formatted = content.trim()

  // If preserveOriginal is true, just return basic line breaks
  if (preserveOriginal) {
    return formatted.replace(/\. ([A-Z])/g, '.\n\n$1')
  }

  // 1. Add line breaks after sentences (but not for abbreviations)
  if (addLineBreaks) {
    formatted = formatted.replace(/\. ([A-Z][^.]*[a-z])/g, '.\n\n$1')
    formatted = formatted.replace(/\? ([A-Z])/g, '?\n\n$1')
    formatted = formatted.replace(/! ([A-Z])/g, '!\n\n$1')
  }

  // 2. Enhanced instruction formatting
  if (enhanceInstructions) {
    // Convert step-by-step instructions to numbered lists
    formatted = formatInstructionalContent(formatted)
    
    // Format questions and requests
    formatted = formatted.replace(
      /(could you (?:kindly |please )?|please |can you )(.*?)(\?|\.)/gi,
      '**$1$2$3**'
    )
  }

  // 3. Highlight technical terms and UI elements
  if (highlightTechnicalTerms) {
    formatted = highlightTechnicalElements(formatted)
  }

  // 4. Format common support patterns
  formatted = formatSupportPatterns(formatted)

  // 5. Clean up excessive whitespace
  formatted = formatted.replace(/\n{3,}/g, '\n\n').trim()

  return formatted
}

/**
 * Converts step-by-step instructions into numbered lists
 */
function formatInstructionalContent(content: string): string {
  // Pattern for sequential instructions
  const instructionPatterns = [
    // "Here is how to find it: In Mailbird, hold down CTRL..."
    /Here is how to ([^:]+):(.*?)(?=\n\n|\. [A-Z][^.]*(?:looking forward|thank you|hope|please|sincerely|best|regards))/gi,
    
    // "Follow these steps: First... Then... Finally..."
    /(follow these steps?|here's how|to do this):(.*?)(?=\n\n|\. (?:We |Please |Thank |Hope |All |Best |Sincerely))/gi
  ]

  instructionPatterns.forEach(pattern => {
    content = content.replace(pattern, (match, intro, instructions) => {
      if (!instructions?.trim()) return match

      // Split into steps based on common indicators
      const stepIndicators = /\. (In |Click |Hold |Open |Please |Make |This |Now |Then |Next |Finally |After )/gi
      const steps = instructions.split(stepIndicators).filter(step => step.trim())

      if (steps.length < 2) return match

      let formatted = `${intro}:\n\n`
      
      steps.forEach((step, index) => {
        if (step.trim()) {
          const cleanStep = step.trim().replace(/^[.:]\s*/, '')
          if (cleanStep) {
            formatted += `${index + 1}. ${cleanStep}\n`
          }
        }
      })

      return formatted
    })
  })

  return content
}

/**
 * Highlights technical terms, file names, and UI elements
 */
function highlightTechnicalElements(content: string): string {
  // File names and extensions
  content = content.replace(/\b([A-Za-z0-9_-]+\.(log|txt|png|jpg|jpeg|pdf|zip|exe|msi))\b/gi, '`$1`')
  
  // Menu items and UI elements in quotes
  content = content.replace(/'([^']+)'/g, '**"$1"**')
  
  // Keyboard shortcuts
  content = content.replace(/\b(CTRL|ALT|SHIFT|CMD|F[0-9]+)\b/gi, '`$1`')
  content = content.replace(/\b(CTRL|ALT|SHIFT|CMD)\s*\+\s*([A-Z0-9]+)/gi, '`$1+$2`')
  
  // Common technical terms
  const technicalTerms = [
    'Windows Explorer', 'Data Directory', 'Mailbird menu', 'log file',
    'error message', 'settings', 'configuration', 'installation'
  ]
  
  technicalTerms.forEach(term => {
    const regex = new RegExp(`\\b${term}\\b`, 'gi')
    content = content.replace(regex, `**${term}**`)
  })

  return content
}

/**
 * Formats common customer support patterns
 */
function formatSupportPatterns(content: string): string {
  // Greeting patterns
  content = content.replace(
    /^(Hello [^,]+),?\s*/,
    '**$1**\n\n'
  )
  
  // Thank you messages
  content = content.replace(
    /(Thank you (?:for |very much for )[^.]+\.)/gi,
    '*$1*'
  )
  
  // Apologies
  content = content.replace(
    /((?:sincere )?apologies? (?:for |if )[^.]+\.)/gi,
    '*$1*'
  )
  
  // Sign-offs
  content = content.replace(
    /((?:We look forward to|All the best|Best regards|Sincerely|Thank you)[^.]*\.?)$/i,
    '\n\n*$1*'
  )

  return content
}

/**
 * Formats customer questions for better readability
 */
export function formatCustomerQuestion(content: string): string {
  if (!content?.trim()) return content

  let formatted = content.trim()

  // Add line breaks after sentences
  formatted = formatted.replace(/\. ([A-Z])/g, '.\n\n$1')
  formatted = formatted.replace(/\? ([A-Z])/g, '?\n\n$1')

  // Highlight technical issues
  formatted = formatted.replace(
    /\b(can't|cannot|won't|doesn't work|not working|error|problem|issue)\b/gi,
    '**$1**'
  )

  return formatted.trim()
}

/**
 * Auto-detects content type and applies appropriate formatting
 */
export function autoFormatContent(content: string, isAnswer: boolean = false): string {
  if (!content?.trim()) return content

  // Check if content already has markdown formatting
  // Note: Exclude parentheses from detection as they appear in URLs and phone numbers
  const hasMarkdown = /[*_`#\[\]]/.test(content) || 
                     content.includes('\n\n') ||
                     content.includes('**') ||
                     content.includes('__') ||
                     content.includes('```')
  
  if (hasMarkdown) {
    return content // Already formatted
  }

  // Apply appropriate formatting based on content type
  if (isAnswer) {
    return formatSupportContent(content, {
      enhanceInstructions: true,
      highlightTechnicalTerms: true,
      addLineBreaks: true
    })
  } else {
    return formatCustomerQuestion(content)
  }
}