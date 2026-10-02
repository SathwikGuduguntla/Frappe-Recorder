// A small Markdown renderer for model-written summaries and SOPs. Everything is
// HTML-escaped first, so model output can never inject markup; times like (2:15)
// become buttons that seek the video.

const escape = (text) =>
  text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')

function inline(text) {
  return escape(text)
    .replace(/`([^`]+)`/g, '<code class="rounded bg-surface-gray-2 px-1">$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/(^|[^*])\*([^*\s][^*]*)\*/g, '$1<em>$2</em>')
    .replace(/\b(?:(\d{1,2}):)?(\d{1,2}):(\d{2})\b/g, (match, h, m, s) => {
      const seconds = Number(h || 0) * 3600 + Number(m) * 60 + Number(s)
      return `<button type="button" data-time="${seconds}" class="rounded bg-surface-green-2 px-1 font-medium tabular-nums text-ink-green-8 hover:underline">${match}</button>`
    })
}

export function renderMarkdown(source) {
  const out = []
  let list = null
  const closeList = () => {
    if (list) out.push(list === 'ol' ? '</ol>' : '</ul>')
    list = null
  }

  for (const raw of (source || '').split('\n')) {
    const line = raw.trimEnd()
    let match
    if (!line.trim()) {
      closeList()
    } else if ((match = line.match(/^(#{1,3})\s+(.*)$/))) {
      closeList()
      const level = match[1].length
      const size = ['text-lg', 'text-base', 'text-base'][level - 1]
      out.push(`<h${level + 2} class="mt-4 mb-1.5 font-semibold text-ink-gray-9 ${size}">${inline(match[2])}</h${level + 2}>`)
    } else if ((match = line.match(/^\s*[-*•]\s+(.*)$/))) {
      if (list !== 'ul') {
        closeList()
        out.push('<ul class="my-1.5 list-disc space-y-1 pl-5">')
        list = 'ul'
      }
      out.push(`<li>${inline(match[1])}</li>`)
    } else if ((match = line.match(/^\s*\d+[.)]\s+(.*)$/))) {
      if (list !== 'ol') {
        closeList()
        out.push('<ol class="my-1.5 list-decimal space-y-1.5 pl-5">')
        list = 'ol'
      }
      out.push(`<li>${inline(match[1])}</li>`)
    } else {
      closeList()
      out.push(`<p class="my-1.5">${inline(line)}</p>`)
    }
  }
  closeList()
  return out.join('')
}
