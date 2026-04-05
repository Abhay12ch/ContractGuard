

/**
 * Renders markdown-formatted text as styled HTML.
 * Supports: **bold**, *italic*, `code`, headings, bullet/numbered lists, and paragraphs.
 */
export const MarkdownText = ({
  text,
  className = '',
}: {
  text: string;
  className?: string;
}) => {
  if (!text) return null;

  const html = markdownToHtml(text);

  return (
    <div
      className={`markdown-body ${className}`}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
};

function markdownToHtml(md: string): string {
  // Split into lines
  const lines = md.split('\n');
  const output: string[] = [];
  let inList = false;
  let listType: 'ul' | 'ol' | '' = '';

  for (let i = 0; i < lines.length; i++) {
    let line = lines[i];

    // Headings: ## Heading or **Heading:** at the start of a line
    const h2Match = line.match(/^#{1,2}\s+(.+)/);
    if (h2Match) {
      closeList();
      output.push(`<h4 class="md-heading">${inlineFormat(h2Match[1])}</h4>`);
      continue;
    }

    // Standalone bold heading-like lines: **Something:**
    const boldHeadingMatch = line.match(/^\*\*(.+?)\*\*\s*$/);
    if (boldHeadingMatch && !line.includes('- ')) {
      closeList();
      output.push(`<h4 class="md-heading">${inlineFormat(boldHeadingMatch[1])}</h4>`);
      continue;
    }

    // Unordered list: - item or * item
    const ulMatch = line.match(/^\s*[-*]\s+(.+)/);
    if (ulMatch) {
      if (!inList || listType !== 'ul') {
        closeList();
        output.push('<ul class="md-list">');
        inList = true;
        listType = 'ul';
      }
      output.push(`<li>${inlineFormat(ulMatch[1])}</li>`);
      continue;
    }

    // Ordered list: 1. item
    const olMatch = line.match(/^\s*\d+[.)]\s+(.+)/);
    if (olMatch) {
      if (!inList || listType !== 'ol') {
        closeList();
        output.push('<ol class="md-list md-list-ordered">');
        inList = true;
        listType = 'ol';
      }
      output.push(`<li>${inlineFormat(olMatch[1])}</li>`);
      continue;
    }

    // Empty line
    if (line.trim() === '') {
      closeList();
      output.push('<div class="md-spacer"></div>');
      continue;
    }

    // Regular paragraph
    closeList();
    output.push(`<p class="md-paragraph">${inlineFormat(line)}</p>`);
  }

  closeList();
  return output.join('\n');

  function closeList() {
    if (inList) {
      output.push(listType === 'ol' ? '</ol>' : '</ul>');
      inList = false;
      listType = '';
    }
  }
}

/** Inline formatting: bold, italic, code, links */
function inlineFormat(text: string): string {
  return text
    // Bold: **text** or __text__
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/__(.+?)__/g, '<strong>$1</strong>')
    // Italic: *text* or _text_ (but not inside words)
    .replace(/(?<!\w)\*([^*]+?)\*(?!\w)/g, '<em>$1</em>')
    .replace(/(?<!\w)_([^_]+?)_(?!\w)/g, '<em>$1</em>')
    // Inline code: `code`
    .replace(/`([^`]+?)`/g, '<code class="md-code">$1</code>')
    // Links: [text](url)
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer" class="md-link">$1</a>');
}
