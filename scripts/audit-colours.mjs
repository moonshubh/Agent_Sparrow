#!/usr/bin/env node

import fs from 'fs/promises';
import path from 'path';
import { fileURLToPath } from 'url';
import { dirname } from 'path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// Color patterns to detect
const PURPLE_PATTERNS = {
  // Hex codes
  hexCodes: [
    /#7e22ce/gi,    // purple-700
    /#8b5cf6/gi,    // purple-500
    /#a855f7/gi,    // purple-500
    /#9333ea/gi,    // purple-600
    /#c084fc/gi,    // purple-400
    /#d8b4fe/gi,    // purple-300
    /#e9d5ff/gi,    // purple-200
    /#f3e8ff/gi,    // purple-100
    /#6b21a8/gi,    // purple-800
    /#581c87/gi,    // purple-900
    /#4c1d95/gi,    // violet-900
    /#5b21b6/gi,    // violet-800
    /#6d28d9/gi,    // violet-700
    /#7c3aed/gi,    // violet-600
    /#8b5cf6/gi,    // violet-500
    /#a78bfa/gi,    // violet-400
    /#c4b5fd/gi,    // violet-300
    /#ddd6fe/gi,    // violet-200
    /#ede9fe/gi,    // violet-100
    /#4338ca/gi,    // indigo-700
    /#6366f1/gi,    // indigo-500
    /#818cf8/gi,    // indigo-400
    /#a5b4fc/gi,    // indigo-300
    /#c7d2fe/gi,    // indigo-200
    /#e0e7ff/gi,    // indigo-100
  ],
  
  // HSL values (hue 250-280)
  hslPatterns: [
    /hsl\(\s*2[5-8]\d\s*,/gi,
    /hsl\(\s*2[5-8]\d\s+/gi,
  ],
  
  // Tailwind classes
  tailwindClasses: [
    /\bpurple-\d{1,3}\b/g,
    /\bindigo-\d{1,3}\b/g,
    /\bviolet-\d{1,3}\b/g,
    /\bbg-purple-\d{1,3}\b/g,
    /\bbg-indigo-\d{1,3}\b/g,
    /\bbg-violet-\d{1,3}\b/g,
    /\btext-purple-\d{1,3}\b/g,
    /\btext-indigo-\d{1,3}\b/g,
    /\btext-violet-\d{1,3}\b/g,
    /\bborder-purple-\d{1,3}\b/g,
    /\bborder-indigo-\d{1,3}\b/g,
    /\bborder-violet-\d{1,3}\b/g,
    /\bhover:.*purple-\d{1,3}\b/g,
    /\bhover:.*indigo-\d{1,3}\b/g,
    /\bhover:.*violet-\d{1,3}\b/g,
  ],
  
  // CSS variables
  cssVariables: [
    /--primary:\s*#[789abcdef]{3,6}/gi,
    /--primary:\s*hsl\([^)]+\)/gi,
    /--purple/gi,
    /--indigo/gi,
    /--violet/gi,
  ]
};

// Mailbird Blue palette (allowed colors)
const MAILBIRD_PALETTE = {
  'mb-blue-50': '#e6f4ff',
  'mb-blue-100': '#bae3ff',
  'mb-blue-200': '#7cc4fa',
  'mb-blue-300': '#47a3f3',
  'mb-blue-400': '#2186eb',
  'mb-blue-500': '#0967d2',
  'mb-blue-600': '#0552b5',
  'mb-blue-700': '#03449e',
  'mb-blue-800': '#01337d',
  'mb-blue-900': '#002159',
  
  // Primary blue
  'primary': '#0095ff',
  'primary-light': '#38b6ff',
  'primary-dark': '#0077cc',
  
  // Allowed neutrals
  'white': '#ffffff',
  'black': '#000000',
  'gray': 'gray',
  'neutral': 'neutral',
  'slate': 'slate',
  'zinc': 'zinc',
};

// Replacement mappings
const REPLACEMENTS = {
  // Hex codes
  '#7e22ce': '#03449e', // purple-700 -> mb-blue-700
  '#8b5cf6': '#0967d2', // purple-500 -> mb-blue-500
  '#a855f7': '#0967d2', // purple-500 -> mb-blue-500
  '#9333ea': '#0552b5', // purple-600 -> mb-blue-600
  '#c084fc': '#2186eb', // purple-400 -> mb-blue-400
  '#d8b4fe': '#47a3f3', // purple-300 -> mb-blue-300
  '#e9d5ff': '#7cc4fa', // purple-200 -> mb-blue-200
  '#f3e8ff': '#bae3ff', // purple-100 -> mb-blue-100
  
  // Tailwind classes
  'purple-': 'mb-blue-',
  'indigo-': 'mb-blue-',
  'violet-': 'mb-blue-',
  
  // For hovers specifically
  'hover:bg-primary/10': 'hover:bg-mb-blue-300/10',
  'hover:bg-primary': 'hover:bg-mb-blue-300',
  'hover:text-primary': 'hover:text-mb-blue-300',
};

class ColourAuditor {
  constructor() {
    this.violations = [];
    this.filesScanned = 0;
    this.fixedCount = 0;
  }
  
  async auditDirectory(dir, options = {}) {
    const entries = await fs.readdir(dir, { withFileTypes: true });
    
    for (const entry of entries) {
      const fullPath = path.join(dir, entry.name);
      
      // Skip node_modules, .next, and other build directories
      if (entry.isDirectory()) {
        if (['node_modules', '.next', 'dist', '.git', 'coverage'].includes(entry.name)) {
          continue;
        }
        await this.auditDirectory(fullPath, options);
      } else if (entry.isFile()) {
        // Only scan relevant files
        const ext = path.extname(entry.name);
        if (['.tsx', '.ts', '.css', '.scss', '.js', '.jsx'].includes(ext)) {
          await this.auditFile(fullPath, options);
        }
      }
    }
  }
  
  async auditFile(filePath, options = {}) {
    this.filesScanned++;
    const content = await fs.readFile(filePath, 'utf-8');
    const violations = [];
    let modifiedContent = content;
    
    // Check for hex codes
    for (const pattern of PURPLE_PATTERNS.hexCodes) {
      const matches = content.match(pattern);
      if (matches) {
        violations.push({
          type: 'hex',
          pattern: pattern.source,
          matches: [...new Set(matches)],
          line: this.findLineNumbers(content, matches)
        });
        
        if (options.autoFix) {
          matches.forEach(match => {
            const replacement = REPLACEMENTS[match.toLowerCase()] || '#0095ff';
            modifiedContent = modifiedContent.replace(new RegExp(match, 'gi'), replacement);
          });
        }
      }
    }
    
    // Check for HSL patterns
    for (const pattern of PURPLE_PATTERNS.hslPatterns) {
      const matches = content.match(pattern);
      if (matches) {
        violations.push({
          type: 'hsl',
          pattern: pattern.source,
          matches: [...new Set(matches)],
          line: this.findLineNumbers(content, matches)
        });
        
        if (options.autoFix) {
          // Replace with HSL equivalent of Mailbird blue
          modifiedContent = modifiedContent.replace(pattern, 'hsl(206,');
        }
      }
    }
    
    // Check for Tailwind classes
    for (const pattern of PURPLE_PATTERNS.tailwindClasses) {
      const matches = content.match(pattern);
      if (matches) {
        violations.push({
          type: 'tailwind',
          pattern: pattern.source,
          matches: [...new Set(matches)],
          line: this.findLineNumbers(content, matches)
        });
        
        if (options.autoFix) {
          matches.forEach(match => {
            // Special handling for hover states
            if (match.includes('hover:')) {
              const colorClass = match.replace('hover:', '');
              const level = colorClass.match(/\d+/)?.[0] || '500';
              const replacement = match.includes('purple') || match.includes('indigo') || match.includes('violet')
                ? `hover:bg-mb-blue-300` // All hovers should use mb-blue-300
                : match;
              modifiedContent = modifiedContent.replace(match, replacement);
            } else {
              // Regular classes
              let replacement = match;
              if (match.includes('purple-')) {
                replacement = match.replace('purple-', 'mb-blue-');
              } else if (match.includes('indigo-')) {
                replacement = match.replace('indigo-', 'mb-blue-');
              } else if (match.includes('violet-')) {
                replacement = match.replace('violet-', 'mb-blue-');
              }
              modifiedContent = modifiedContent.replace(match, replacement);
            }
          });
        }
      }
    }
    
    // Check CSS variables
    for (const pattern of PURPLE_PATTERNS.cssVariables) {
      const matches = content.match(pattern);
      if (matches) {
        violations.push({
          type: 'css-variable',
          pattern: pattern.source,
          matches: [...new Set(matches)],
          line: this.findLineNumbers(content, matches)
        });
        
        if (options.autoFix) {
          // Replace --primary with Mailbird blue
          modifiedContent = modifiedContent.replace(/--primary:\s*[^;]+/gi, '--primary: #0095ff');
        }
      }
    }
    
    // Check for hover states not using mb-blue-300 (more comprehensive)
    const hoverPatterns = [
      /hover:bg-mb-blue(?!-\d)/g,      // hover:bg-mb-blue (not followed by number)
      /hover:text-mb-blue(?!-\d)/g,    // hover:text-mb-blue (not followed by number) 
      /hover:border-mb-blue(?!-\d)/g,  // hover:border-mb-blue (not followed by number)
      /hover:from-mb-blue(?!-\d)/g,    // hover:from-mb-blue (not followed by number)
      /hover:[a-z-]+-(primary|accent)(?!-foreground)/g, // hover with primary/accent (but not primary-foreground)
      /hover:bg-blue(?!-\d)/g,         // hover:bg-blue (standalone)
    ];
    
    for (const pattern of hoverPatterns) {
      const hoverMatches = content.match(pattern);
      if (hoverMatches) {
        violations.push({
          type: 'hover-state',
          pattern: 'hover states not using mb-blue-300',
          matches: [...new Set(hoverMatches)],
          line: this.findLineNumbers(content, hoverMatches)
        });
        
        if (options.autoFix) {
          hoverMatches.forEach(match => {
            let replacement;
            if (match.includes('text-mb-blue')) {
              replacement = 'hover:text-mb-blue-300';
            } else if (match.includes('border-mb-blue')) {
              replacement = 'hover:border-mb-blue-300';
            } else if (match.includes('from-mb-blue')) {
              replacement = 'hover:from-mb-blue-300';
            } else if (match.includes('primary') || match.includes('accent') || match.includes('blue')) {
              replacement = 'hover:bg-mb-blue-300';
            } else {
              replacement = 'hover:bg-mb-blue-300';
            }
            modifiedContent = modifiedContent.replace(new RegExp(match.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'g'), replacement);
          });
        }
      }
    }
    
    if (violations.length > 0) {
      this.violations.push({
        file: filePath,
        violations
      });
      
      if (options.autoFix && modifiedContent !== content) {
        await fs.writeFile(filePath, modifiedContent);
        this.fixedCount++;
        console.log(`✅ Fixed ${filePath}`);
      }
    }
  }
  
  findLineNumbers(content, matches) {
    const lines = content.split('\n');
    const lineNumbers = [];
    
    matches.forEach(match => {
      lines.forEach((line, index) => {
        if (line.includes(match)) {
          lineNumbers.push(index + 1);
        }
      });
    });
    
    return [...new Set(lineNumbers)];
  }
  
  generateReport() {
    console.log('\n🔍 COLOUR AUDIT REPORT\n');
    console.log(`Files scanned: ${this.filesScanned}`);
    console.log(`Violations found: ${this.violations.length} files with issues`);
    console.log(`Files auto-fixed: ${this.fixedCount}\n`);
    
    if (this.violations.length === 0) {
      console.log('✅ No purple/indigo/violet colors found! All clear.\n');
      return;
    }
    
    console.log('❌ VIOLATIONS FOUND:\n');
    
    this.violations.forEach(({ file, violations }) => {
      console.log(`📄 ${file}`);
      violations.forEach(({ type, matches, line }) => {
        console.log(`   Type: ${type}`);
        console.log(`   Matches: ${matches.join(', ')}`);
        console.log(`   Lines: ${line.join(', ')}`);
      });
      console.log('');
    });
    
    // Generate summary
    const totalViolations = this.violations.reduce((sum, v) => sum + v.violations.length, 0);
    console.log(`\n📊 SUMMARY: ${totalViolations} total violations in ${this.violations.length} files\n`);
  }
  
  async generatePatchFile() {
    if (this.violations.length === 0) return null;
    
    const patchContent = [];
    patchContent.push('# Colour Fix Patch\n');
    patchContent.push(`# Generated: ${new Date().toISOString()}\n`);
    patchContent.push(`# Files with violations: ${this.violations.length}\n\n`);
    
    for (const { file, violations } of this.violations) {
      patchContent.push(`## ${file}\n`);
      violations.forEach(({ type, matches }) => {
        patchContent.push(`- ${type}: ${matches.join(', ')}\n`);
      });
      patchContent.push('\n');
    }
    
    const patchPath = path.join(dirname(__dirname), 'dist', 'Colour_Fix_Patch.diff');
    await fs.mkdir(path.dirname(patchPath), { recursive: true });
    await fs.writeFile(patchPath, patchContent.join(''));
    
    return patchPath;
  }
  
  async generateAuditReport() {
    const reportContent = [];
    reportContent.push('# Colour Audit Verification Report\n');
    reportContent.push(`Generated: ${new Date().toISOString()}\n\n`);
    
    reportContent.push('## Summary\n');
    reportContent.push(`- Files Scanned: ${this.filesScanned}\n`);
    reportContent.push(`- Violations Found: ${this.violations.length} files\n`);
    reportContent.push(`- Auto-Fixed: ${this.fixedCount} files\n`);
    reportContent.push(`- Status: ${this.violations.length === 0 ? '✅ PASS' : '❌ FAIL'}\n\n`);
    
    if (this.violations.length > 0) {
      reportContent.push('## Violations Detail\n\n');
      
      this.violations.forEach(({ file, violations }) => {
        reportContent.push(`### ${file}\n`);
        violations.forEach(({ type, matches, line }) => {
          reportContent.push(`- **Type**: ${type}\n`);
          reportContent.push(`- **Matches**: \`${matches.join('`, `')}\`\n`);
          reportContent.push(`- **Lines**: ${line.join(', ')}\n\n`);
        });
      });
    }
    
    reportContent.push('## Mailbird Palette Reference\n');
    reportContent.push('```css\n');
    Object.entries(MAILBIRD_PALETTE).forEach(([name, value]) => {
      reportContent.push(`--${name}: ${value};\n`);
    });
    reportContent.push('```\n');
    
    const reportPath = path.join(dirname(__dirname), 'docs', 'Audit_Verification.md');
    await fs.mkdir(path.dirname(reportPath), { recursive: true });
    await fs.writeFile(reportPath, reportContent.join(''));
    
    return reportPath;
  }
}

// CLI
async function main() {
  const args = process.argv.slice(2);
  const options = {
    autoFix: args.includes('--fix'),
    path: args.find(arg => !arg.startsWith('--')) || path.join(dirname(__dirname), 'frontend')
  };
  
  console.log('🎨 Mailbird Colour Auditor\n');
  console.log(`Scanning: ${options.path}`);
  console.log(`Auto-fix: ${options.autoFix ? 'Enabled' : 'Disabled'}\n`);
  
  const auditor = new ColourAuditor();
  
  try {
    await auditor.auditDirectory(options.path, options);
    auditor.generateReport();
    
    const patchPath = await auditor.generatePatchFile();
    if (patchPath) {
      console.log(`📝 Patch file generated: ${patchPath}`);
    }
    
    const reportPath = await auditor.generateAuditReport();
    console.log(`📊 Audit report generated: ${reportPath}`);
    
    // Exit with error code if violations found and not auto-fixing
    if (auditor.violations.length > 0 && !options.autoFix) {
      console.log('\n💡 Run with --fix flag to automatically fix violations');
      process.exit(1);
    }
  } catch (error) {
    console.error('❌ Error during audit:', error);
    process.exit(1);
  }
}

main();