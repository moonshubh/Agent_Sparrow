// Markdown ↔ HTML helpers used to bridge TipTap (HTML) with Markdown storage
import { marked } from 'marked'
import TurndownService from 'turndown'

const turndown = new TurndownService({ headingStyle: 'atx', codeBlockStyle: 'fenced' })

export function mdToHtml(md: string): string {
  try {
    return marked.parse(md || '') as string
  } catch (e) {
    console.error('mdToHtml failed', e)
    return md || ''
  }
}

export function htmlToMd(html: string): string {
  try {
    return turndown.turndown(html || '')
  } catch (e) {
    console.error('htmlToMd failed', e)
    return html || ''
  }
}

