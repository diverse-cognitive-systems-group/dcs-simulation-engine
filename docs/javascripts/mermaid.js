let mermaidInitialized = false

function promoteMermaidCodeBlocks(root) {
  const codeBlocks = root.querySelectorAll('pre > code.language-mermaid')
  for (const codeBlock of codeBlocks) {
    const pre = codeBlock.parentElement
    if (!pre || pre.dataset.mermaidPromoted === 'true') {
      continue
    }

    const container = document.createElement('div')
    container.className = 'mermaid'
    container.textContent = codeBlock.textContent || ''
    pre.dataset.mermaidPromoted = 'true'
    pre.replaceWith(container)
  }

  const legacyBlocks = root.querySelectorAll('pre.mermaid')
  for (const pre of legacyBlocks) {
    if (pre.dataset.mermaidPromoted === 'true') {
      continue
    }

    const container = document.createElement('div')
    container.className = 'mermaid'
    container.textContent = pre.textContent || ''
    pre.dataset.mermaidPromoted = 'true'
    pre.replaceWith(container)
  }
}

async function renderMermaid(root = document) {
  if (!window.mermaid) {
    return
  }

  if (!mermaidInitialized) {
    window.mermaid.initialize({
      startOnLoad: false,
      securityLevel: 'loose',
      theme: 'default',
    })
    mermaidInitialized = true
  }

  promoteMermaidCodeBlocks(root)

  const diagrams = root.querySelectorAll('.mermaid')
  if (diagrams.length === 0) {
    return
  }

  await window.mermaid.run({
    nodes: Array.from(diagrams),
  })
}

if (window.document$) {
  window.document$.subscribe(() => {
    void renderMermaid()
  })
} else {
  window.addEventListener('load', () => {
    void renderMermaid()
  })
}
