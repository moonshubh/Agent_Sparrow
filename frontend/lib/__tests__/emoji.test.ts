import { describe, it, expect } from 'vitest'
import { sectionIcon, sectionPatterns, accessibleEmoji, NBSP } from '../emoji'

describe('emoji utility', () => {
  describe('sectionIcon', () => {
    it('defines correct icons for each section type', () => {
      expect(sectionIcon.summary).toBe('📝')
      expect(sectionIcon.issues).toBe('🚩')
      expect(sectionIcon.fixes).toBe('💡')
    })
  })

  describe('sectionPatterns', () => {
    it('matches executive summary patterns', () => {
      const summaryPattern = sectionPatterns.find(p => p.emoji === sectionIcon.summary)
      expect(summaryPattern).toBeDefined()
      
      expect(summaryPattern!.pattern.test('Executive Summary')).toBe(true)
      expect(summaryPattern!.pattern.test('EXECUTIVE SUMMARY')).toBe(true)
      expect(summaryPattern!.pattern.test('summary')).toBe(true)
      expect(summaryPattern!.pattern.test('Summary')).toBe(true)
      expect(summaryPattern!.pattern.test('Other Summary')).toBe(false)
    })

    it('matches issues patterns', () => {
      const issuesPattern = sectionPatterns.find(p => p.emoji === sectionIcon.issues)
      expect(issuesPattern).toBeDefined()
      
      expect(issuesPattern!.pattern.test('Key Issues Identified')).toBe(true)
      expect(issuesPattern!.pattern.test('Issues Found')).toBe(true)
      expect(issuesPattern!.pattern.test('Identified Issues')).toBe(true)
      expect(issuesPattern!.pattern.test('Problems Detected')).toBe(true)
      expect(issuesPattern!.pattern.test('issues')).toBe(true)
      expect(issuesPattern!.pattern.test('Random Issues')).toBe(false)
    })

    it('matches solutions patterns', () => {
      const fixesPattern = sectionPatterns.find(p => p.emoji === sectionIcon.fixes)
      expect(fixesPattern).toBeDefined()
      
      expect(fixesPattern!.pattern.test('Recommended Solutions')).toBe(true)
      expect(fixesPattern!.pattern.test('Solutions')).toBe(true)
      expect(fixesPattern!.pattern.test('Fixes')).toBe(true)
      expect(fixesPattern!.pattern.test('Recommendations')).toBe(true)
      expect(fixesPattern!.pattern.test('solution')).toBe(true)
      expect(fixesPattern!.pattern.test('Possible Solutions')).toBe(false)
    })

    it('patterns are case insensitive', () => {
      sectionPatterns.forEach(pattern => {
        // Test that each pattern is case insensitive
        expect(pattern.pattern.flags).toContain('i')
      })
    })
  })

  describe('accessibleEmoji', () => {
    it('wraps emoji in proper accessibility markup', () => {
      const result = accessibleEmoji('📝', 'document')
      expect(result).toBe('<span role="img" aria-label="document">📝</span>')
    })

    it('handles special characters in label', () => {
      const result = accessibleEmoji('🚩', 'warning & alert')
      expect(result).toBe('<span role="img" aria-label="warning &amp; alert">🚩</span>')
    })
  })

  describe('NBSP', () => {
    it('is a non-breaking space character', () => {
      expect(NBSP).toBe('\u00A0')
      expect(NBSP.charCodeAt(0)).toBe(160)
    })
  })
})