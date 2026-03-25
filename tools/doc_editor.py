#!/Users/srinivas/venv/bin/python3
"""
Native Doc Editor Tool - SQLite Version
Programmatic CRUD for docs stored in data/docs.db
Replaces doc_editor.py JSON backend with SQLite
"""

import json
import logging
import os
import re
import sqlite3
import uuid
from datetime import datetime

try:
    from writing_linter import lint
except ImportError:
    from tools.writing_linter import lint

from whoosh import index
from whoosh.fields import Schema, TEXT, ID, NUMERIC
from whoosh.qparser import MultifieldParser, QueryParser, AndGroup
from whoosh.analysis import StemmingAnalyzer
from whoosh import scoring

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WHOOSH_INDEX_DIR = os.path.join(BASE_DIR, "data", "whoosh_index")
DB_PATH = os.path.join(BASE_DIR, "data", "docs.db")

# Track database modification time for automatic reindexing
_last_index_mtime = 0
INDEX_MTIME_MARKER = os.path.join(BASE_DIR, "data", "whoosh_index", ".last_build_mtime")


def get_db():
    """Get SQLite connection with Row factory for dict-like access. Auto-creates table on first use."""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE IF NOT EXISTS docs (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        content TEXT DEFAULT '',
        collection TEXT DEFAULT 'Notes',
        meta_description TEXT DEFAULT '',
        word_count INTEGER DEFAULT 0,
        description TEXT DEFAULT '',
        status TEXT DEFAULT '',
        campaign_id TEXT DEFAULT '',
        published_url TEXT DEFAULT '',
        outline_id TEXT DEFAULT '',
        stitched_from TEXT DEFAULT '',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        last_action TEXT DEFAULT ''
    )""")
    # Seed a welcome doc if table is empty (fresh install)
    count = conn.execute("SELECT COUNT(*) FROM docs").fetchone()[0]
    if count == 0:
        import uuid
        now = datetime.now().isoformat()
        doc_id = f"doc_{uuid.uuid4().hex[:8]}"
        welcome_content = """<h2>Welcome to the OrchestrateOS Doc Editor</h2>
<p>This is your document editor — a single place for all your notes, SOPs, reports, and deliverables.</p>
<h3>What you can do here</h3>
<ul>
<li><strong>Create docs</strong> — click the + button or press Cmd+N</li>
<li><strong>Organize by collection</strong> — type #collection-name in the editor to auto-sort (e.g. #projects, #notes, #logs)</li>
<li><strong>Link docs together</strong> — type @ to mention and link to other documents</li>
<li><strong>Search everything</strong> — press Cmd+K for instant search across all your docs</li>
<li><strong>Format with markdown</strong> — type # for headings, - for lists, > for quotes, ``` for code blocks</li>
</ul>
<h3>Using it with Claude</h3>
<p>Ask Claude to create, search, or update docs for you. For example:</p>
<ul>
<li>"Create a doc called Weekly Report in the Projects collection"</li>
<li>"Search my docs for anything about onboarding"</li>
<li>"Add a section to my SOP doc about client reporting"</li>
</ul>
<p>Everything saves automatically as you type. Press Escape to return to the document list.</p>"""
        conn.execute(
            "INSERT INTO docs (id, title, content, collection, word_count, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (doc_id, "How the OrchestrateOS Doc Editor Works", welcome_content, "Getting Started", 150, now, now)
        )
    conn.commit()
    return conn


def _row_to_dict(row):
    """Convert sqlite3.Row to dict."""
    if row is None:
        return None
    return dict(row)


def _get_semantic_search():
    """Lazy-load semantic_search from docs_vector_indexer."""
    from docs_vector_indexer import semantic_search
    return semantic_search


def _count_words(content: str) -> int:
    """Count words in content after stripping HTML tags."""
    if not content:
        return 0
    # Strip HTML tags
    text = re.sub(r'<[^>]+>', ' ', content)
    # Normalize whitespace and count words
    words = text.split()
    return len(words)


def _extract_meta_description(content: str) -> tuple:
    """Extract meta_description from content if ---summary--- marker is present.

    Args:
        content: The document content to scan

    Returns:
        tuple: (cleaned_content, meta_description or None)
    """
    if not content:
        return content, None

    # Regex to find ---summary--- marker (case-insensitive) and capture everything after it
    pattern = re.compile(r'---summary---\s*(.+?)\s*$', re.DOTALL | re.IGNORECASE)
    match = pattern.search(content)

    if match:
        meta_description = match.group(1).strip()
        # Strip any HTML tags that may have been captured
        meta_description = re.sub(r'<[^>]+>', '', meta_description).strip()
        # Remove the marker and summary from content
        cleaned_content = content[:match.start()].rstrip()
        return cleaned_content, meta_description

    return content, None


def _snapshot_revision(conn, doc_id: str, content: str) -> int:
    """Snapshot current content as a new revision.

    Args:
        conn: Active database connection
        doc_id: Document ID to snapshot
        content: Content to save as revision

    Returns:
        The new revision number
    """
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COALESCE(MAX(revision_number), 0) FROM revisions WHERE doc_id = ?",
        (doc_id,)
    )
    max_rev = cursor.fetchone()[0]
    new_rev = max_rev + 1

    cursor.execute(
        "INSERT INTO revisions (doc_id, revision_number, content, created_at) VALUES (?, ?, ?, ?)",
        (doc_id, new_rev, content, datetime.now().isoformat())
    )
    return new_rev


def _render_table(rows: list) -> str:
    """Render table rows as HTML table with styling.

    First row is treated as header if there are 2+ rows.
    """
    if not rows:
        return ''

    html = ['<table class="md-table" style="border-collapse:collapse;width:100%;margin:16px 0;">']

    for i, cells in enumerate(rows):
        html.append('<tr>')
        tag = 'th' if i == 0 and len(rows) > 1 else 'td'
        style = 'border:1px solid var(--border-color,#333);padding:8px 12px;text-align:left;'
        if i == 0 and len(rows) > 1:
            style += 'background:var(--bg-tertiary,#1A1A1E);font-weight:600;'
        for cell in cells:
            html.append(f'<{tag} style="{style}">{cell}</{tag}>')
        html.append('</tr>')

    html.append('</table>')
    return '\n'.join(html)


def markdown_to_html(text: str) -> str:
    """Convert markdown to HTML for doc editor compatibility."""
    if not text:
        return text

    lines = text.split('\n')
    html_lines = []
    in_code_block = False
    in_list = False
    list_type = None
    in_table = False
    table_rows = []

    for line in lines:
        # Code blocks
        if line.strip().startswith('```'):
            if in_code_block:
                html_lines.append('</code></pre>')
                in_code_block = False
            else:
                html_lines.append('<pre><code>')
                in_code_block = True
            continue

        if in_code_block:
            html_lines.append(line)
            continue

        # Close list if we hit a non-list line
        if in_list and not line.strip().startswith(('-', '*', '1.', '2.', '3.', '4.', '5.', '6.', '7.', '8.', '9.')):
            if not line.strip().startswith((' ', '\t')) or not line.strip():
                html_lines.append(f'</{list_type}>')
                in_list = False
                list_type = None

        # Headers
        if line.startswith('#### '):
            html_lines.append(f'<h4>{line[5:]}</h4>')
        elif line.startswith('### '):
            html_lines.append(f'<h3>{line[4:]}</h3>')
        elif line.startswith('## '):
            html_lines.append(f'<h2>{line[3:]}</h2>')
        elif line.startswith('# '):
            html_lines.append(f'<h1>{line[2:]}</h1>')
        # Blockquotes
        elif line.startswith('> '):
            html_lines.append(f'<blockquote>{line[2:]}</blockquote>')
        # Unordered lists
        elif line.strip().startswith('- ') or line.strip().startswith('* '):
            if not in_list or list_type != 'ul':
                if in_list:
                    html_lines.append(f'</{list_type}>')
                html_lines.append('<ul>')
                in_list = True
                list_type = 'ul'
            content = line.strip()[2:]
            html_lines.append(f'<li>{content}</li>')
        # Ordered lists
        elif re.match(r'^\d+\.\s', line.strip()):
            if not in_list or list_type != 'ol':
                if in_list:
                    html_lines.append(f'</{list_type}>')
                html_lines.append('<ol>')
                in_list = True
                list_type = 'ol'
            content = re.sub(r'^\d+\.\s', '', line.strip())
            html_lines.append(f'<li>{content}</li>')
        # Horizontal rule (but not table separator like |---|---|)
        elif line.strip() in ('---', '***', '___') and '|' not in line:
            html_lines.append('<hr>')
        # Table rows (pipe-delimited)
        elif '|' in line and line.strip().startswith('|') and line.strip().endswith('|'):
            # Close any open list first
            if in_list:
                html_lines.append(f'</{list_type}>')
                in_list = False
                list_type = None

            # Check if this is a separator row (|---|---|)
            cells = [c.strip() for c in line.strip()[1:-1].split('|')]
            is_separator = all(re.match(r'^:?-+:?$', c) for c in cells if c)

            if is_separator:
                # This is the separator row after header
                if table_rows:
                    # First row was header, mark it
                    in_table = True
            else:
                # Regular data row
                table_rows.append(cells)

                # Check if next line is NOT a table row - then close table
                # We'll handle table closing in a post-process step
                in_table = True
        # Empty line - may need to close table
        elif not line.strip():
            # Close table if we were in one
            if in_table and table_rows:
                html_lines.append(_render_table(table_rows))
                table_rows = []
                in_table = False
            continue
        # Regular paragraph
        else:
            # Close table if we were in one
            if in_table and table_rows:
                html_lines.append(_render_table(table_rows))
                table_rows = []
                in_table = False
            html_lines.append(f'<p>{line}</p>')

    # Close any open list
    if in_list:
        html_lines.append(f'</{list_type}>')

    # Close any open code block
    if in_code_block:
        html_lines.append('</code></pre>')

    # Close any open table
    if in_table and table_rows:
        html_lines.append(_render_table(table_rows))

    html = '\n'.join(html_lines)

    # Inline formatting
    html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html)
    html = re.sub(r'\*(.+?)\*', r'<em>\1</em>', html)
    html = re.sub(r'`([^`]+)`', r'<code>\1</code>', html)

    # Wiki links [[Title]] -> doc-link spans with lookup
    html = _convert_wiki_links(html)

    return html


def _convert_wiki_links(html: str) -> str:
    """Convert [[Title]] wiki links to doc-link spans with doc_id lookup.

    Capitalizes the display text when the link:
    1. Is at the start of a paragraph (immediately after <p>)
    2. Starts a new sentence (immediately after '. ')
    """
    def replace_wiki_link(match):
        title = match.group(1)
        # Look up doc by exact title match
        doc_id = _lookup_doc_by_title(title)
        lowercase_title = title.lower()
        return f'<span class="doc-link" data-doc-id="{doc_id}" data-doc-title="{title}" contenteditable="false" title="{title}">{lowercase_title}</span>'

    # First pass: convert all wiki links to spans with lowercase
    html = re.sub(r'\[\[([^\]]+)\]\]', replace_wiki_link, html)

    # Second pass: capitalize doc-link spans that start a paragraph
    # Pattern: <p> followed immediately by a doc-link span
    def capitalize_span_text(match):
        before = match.group(1)
        span_start = match.group(2)
        display_text = match.group(3)
        span_end = match.group(4)
        # Capitalize first letter of display text
        capitalized = display_text[0].upper() + display_text[1:] if display_text else display_text
        return f'{before}{span_start}{capitalized}{span_end}'

    # Capitalize spans right after <p>
    html = re.sub(
        r'(<p>)(<span class="doc-link"[^>]*>)([^<]+)(</span>)',
        capitalize_span_text,
        html
    )

    # Capitalize spans right after ". " (period + space = new sentence)
    html = re.sub(
        r'(\. )(<span class="doc-link"[^>]*>)([^<]+)(</span>)',
        capitalize_span_text,
        html
    )

    return html


def _lookup_doc_by_title(title: str) -> str:
    """Look up a document by exact title match. Returns doc_id or empty string."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM docs WHERE LOWER(title) = LOWER(?)", (title,))
    row = cursor.fetchone()
    conn.close()
    return row['id'] if row else ""


def resolve_collection(input_collection: str) -> str:
    """
    Resolve collection name to match existing collections.

    Normalizes input (strips hyphens/underscores, collapses spaces, title case)
    and matches against existing collection names. Returns the original existing
    collection name if found, otherwise returns the input as-is.

    Examples:
        'permanent notes' -> 'Permanent Notes'
        'permanent-notes' -> 'Permanent Notes'
        'permanent_notes' -> 'Permanent Notes'
        'PermanentNotes' -> 'Permanent Notes'
    """
    if not input_collection:
        return "Notes"  # Default collection

    def normalize(name: str) -> str:
        """Normalize collection name for comparison."""
        # Replace hyphens and underscores with spaces
        normalized = name.replace('-', ' ').replace('_', ' ')
        # Insert space before capital letters for CamelCase (e.g., PermanentNotes -> Permanent Notes)
        normalized = re.sub(r'([a-z])([A-Z])', r'\1 \2', normalized)
        # Collapse multiple spaces and strip
        normalized = ' '.join(normalized.split())
        # Title case and lowercase for comparison
        return normalized.lower()

    input_normalized = normalize(input_collection)

    # Load existing collections from SQLite
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT collection FROM docs")
    existing_collections = set(row['collection'] for row in cursor.fetchall())
    conn.close()

    # Find matching collection
    for existing in existing_collections:
        if normalize(existing) == input_normalized:
            return existing  # Return original casing

    # No match found - return input with title case normalization
    # Apply same normalization but return in title case
    cleaned = input_collection.replace('-', ' ').replace('_', ' ')
    cleaned = re.sub(r'([a-z])([A-Z])', r'\1 \2', cleaned)
    cleaned = ' '.join(cleaned.split())
    return cleaned.title()


def ensure_link_fields(doc):
    """Non-destructively add links/backlinks fields if missing."""
    if "links" not in doc:
        doc["links"] = []
    if "backlinks" not in doc:
        doc["backlinks"] = []
    return doc


def link_docs(source_doc_id: str, target_doc_id: str) -> dict:
    """
    Create bidirectional link from source to target.
    Adds entry to links table.

    Args:
        source_doc_id: The doc containing the link
        target_doc_id: The doc being linked to

    Returns:
        {status, message}
    """
    if source_doc_id == target_doc_id:
        return {"status": "error", "message": "Cannot link doc to itself"}

    conn = get_db()
    cursor = conn.cursor()

    # Check both docs exist
    cursor.execute("SELECT id, title FROM docs WHERE id = ?", (source_doc_id,))
    source = cursor.fetchone()
    if not source:
        conn.close()
        return {"status": "error", "message": f"Source doc {source_doc_id} not found"}

    cursor.execute("SELECT id, title FROM docs WHERE id = ?", (target_doc_id,))
    target = cursor.fetchone()
    if not target:
        conn.close()
        return {"status": "error", "message": f"Target doc {target_doc_id} not found"}

    # Insert link (ignore if already exists)
    try:
        cursor.execute(
            "INSERT OR IGNORE INTO links (source_id, target_id) VALUES (?, ?)",
            (source_doc_id, target_doc_id)
        )
        conn.commit()
    except sqlite3.Error as e:
        conn.close()
        return {"status": "error", "message": str(e)}

    conn.close()

    return {
        "status": "success",
        "message": f"Linked {source['title']} → {target['title']}",
        "source_doc_id": source_doc_id,
        "target_doc_id": target_doc_id
    }


def unlink_docs(source_doc_id: str, target_doc_id: str) -> dict:
    """
    Remove bidirectional link between docs.

    Args:
        source_doc_id: The doc that had the link
        target_doc_id: The doc that was linked to

    Returns:
        {status, message}
    """
    conn = get_db()
    cursor = conn.cursor()

    # Check both docs exist
    cursor.execute("SELECT id, title FROM docs WHERE id = ?", (source_doc_id,))
    source = cursor.fetchone()
    if not source:
        conn.close()
        return {"status": "error", "message": f"Source doc {source_doc_id} not found"}

    cursor.execute("SELECT id, title FROM docs WHERE id = ?", (target_doc_id,))
    target = cursor.fetchone()
    if not target:
        conn.close()
        return {"status": "error", "message": f"Target doc {target_doc_id} not found"}

    # Delete link
    cursor.execute(
        "DELETE FROM links WHERE source_id = ? AND target_id = ?",
        (source_doc_id, target_doc_id)
    )
    conn.commit()
    conn.close()

    return {
        "status": "success",
        "message": f"Unlinked {source['title']} ↛ {target['title']}"
    }


def read_backlinks(doc_id: str) -> dict:
    """
    Get all docs that link TO this doc.

    Args:
        doc_id: The document ID

    Returns:
        {status, backlinks: [{id, title, collection}]}
    """
    conn = get_db()
    cursor = conn.cursor()

    # Check doc exists
    cursor.execute("SELECT id FROM docs WHERE id = ?", (doc_id,))
    if not cursor.fetchone():
        conn.close()
        return {"status": "error", "message": f"Doc {doc_id} not found"}

    # Get all docs that link to this doc
    cursor.execute("""
        SELECT d.id, d.title, d.collection
        FROM links l
        JOIN docs d ON l.source_id = d.id
        WHERE l.target_id = ?
    """, (doc_id,))

    backlinks = []
    for row in cursor.fetchall():
        backlinks.append({
            "id": row['id'],
            "title": row['title'],
            "collection": row['collection']
        })

    conn.close()

    return {
        "status": "success",
        "doc_id": doc_id,
        "backlinks": backlinks,
        "count": len(backlinks)
    }


def read_links(doc_id: str) -> dict:
    """
    Get all docs that this doc links TO.

    Args:
        doc_id: The document ID

    Returns:
        {status, links: [{id, title, collection}]}
    """
    conn = get_db()
    cursor = conn.cursor()

    # Check doc exists
    cursor.execute("SELECT id FROM docs WHERE id = ?", (doc_id,))
    if not cursor.fetchone():
        conn.close()
        return {"status": "error", "message": f"Doc {doc_id} not found"}

    # Get all docs this doc links to
    cursor.execute("""
        SELECT d.id, d.title, d.collection
        FROM links l
        JOIN docs d ON l.target_id = d.id
        WHERE l.source_id = ?
    """, (doc_id,))

    links = []
    for row in cursor.fetchall():
        links.append({
            "id": row['id'],
            "title": row['title'],
            "collection": row['collection']
        })

    conn.close()

    return {
        "status": "success",
        "doc_id": doc_id,
        "links": links,
        "count": len(links)
    }


def create_doc(title: str, content: str, collection: str = "Notes", convert_markdown: bool = True) -> dict:
    """
    Create a new document.

    Args:
        title: Document title
        content: Document content (markdown or HTML)
        collection: Collection name (Notes, Permanent Notes, Projects, Logs, Resources, Inbox)
        convert_markdown: If True, convert markdown to HTML (default True)

    Returns:
        {"status": "success", "doc_id": "doc_xxx", "message": "..."}
    """
    doc_id = f"doc_{uuid.uuid4().hex[:8]}"
    now = datetime.now().isoformat()

    # Resolve collection to match existing collection names
    collection = resolve_collection(collection)

    # Extract meta_description if ---summary--- marker is present
    content, meta_description = _extract_meta_description(content)

    # Convert markdown to HTML if needed
    html_content = markdown_to_html(content) if convert_markdown else content

    # Auto-lint content for AI writing patterns
    lint_result = lint(html_content)
    html_content = lint_result.get("fixed_text", html_content)
    lint_changes = lint_result.get("change_log", [])

    # Strip duplicate H1 title if agents passed title both as param AND as H1 in content
    h1_pattern = re.compile(r'^<h1>([^<]+)</h1>\s*', re.IGNORECASE)
    h1_match = h1_pattern.match(html_content)
    if h1_match and h1_match.group(1).strip().lower() == title.strip().lower():
        html_content = html_content[h1_match.end():]

    # Strip leading collection hashtag lines like <p>#newsletter</p> or <p>#newsletters</p>
    hashtag_pattern = re.compile(r'^<p>#\w+</p>\s*', re.IGNORECASE)
    while hashtag_pattern.match(html_content):
        html_content = hashtag_pattern.sub('', html_content, count=1)

    # Calculate word count
    word_count = _count_words(html_content)

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO docs (id, title, content, collection, meta_description, word_count, created_at, updated_at, last_action)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (doc_id, title, html_content, collection, meta_description or '', word_count, now, now, 'content_update'))

    conn.commit()
    conn.close()

    # Auto-sync content calendar for content collections
    if collection.lower() in ['blogs', 'video', 'newsletters']:
        sync_content_calendar()

    result = {
        "status": "success",
        "doc_id": doc_id,
        "message": f"Created doc '{title}' in {collection}"
    }

    if not meta_description:
        result['message'] += f'. BEFORE logging this task complete: append a ---summary--- to {doc_id} using docs.append_doc with a 1-2 sentence summary of this docs content.'

    if lint_changes:
        result["lint_changes"] = lint_changes
    return result


def update_doc(doc_id: str, find: str, replace: str, title: str = None, collection: str = None) -> dict:
    """
    Update an existing document with find-and-replace.

    Args:
        doc_id: The document ID to update
        find: The string to find in the document content
        replace: The string to replace it with
        title: New title (optional)
        collection: New collection (optional)

    Returns:
        {"status": "success/error", "message": "..."}
    """
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT id, title, content, collection FROM docs WHERE id = ?", (doc_id,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        return {"status": "error", "message": f"Doc {doc_id} not found"}

    doc = _row_to_dict(row)
    content = doc.get("content", "")

    # Count occurrences
    count = content.count(find)

    if count == 0:
        conn.close()
        return {"status": "error", "message": f"Content not found: '{find[:50]}...' was not found in the document"}

    if count > 1:
        conn.close()
        return {"status": "error", "message": f"Ambiguous match: '{find[:50]}...' appears {count} times. Provide a more specific string."}

    # Snapshot current content as revision before making changes
    _snapshot_revision(conn, doc_id, content)

    # Auto-lint the replacement content for AI writing patterns
    lint_result = lint(replace)
    linted_replace = lint_result.get("fixed_text", replace)
    lint_changes = lint_result.get("change_log", [])

    # Perform the replacement
    new_content = content.replace(find, linted_replace, 1)

    # Extract meta_description if ---summary--- marker is present in the updated content
    new_content, meta_description = _extract_meta_description(new_content)

    # Calculate word count
    word_count = _count_words(new_content)
    now = datetime.now().isoformat()

    new_title = title if title is not None else doc['title']
    new_collection = resolve_collection(collection) if collection is not None else doc['collection']

    cursor.execute("""
        UPDATE docs
        SET content = ?, title = ?, collection = ?, meta_description = COALESCE(?, meta_description),
            word_count = ?, updated_at = ?, last_action = ?
        WHERE id = ?
    """, (new_content, new_title, new_collection, meta_description, word_count, now, 'content_update', doc_id))

    conn.commit()
    conn.close()

    result = {
        "status": "success",
        "message": f"Updated doc '{new_title}' - replaced 1 occurrence"
    }
    if lint_changes:
        result["lint_changes"] = lint_changes
    return result


def replace_section(doc_id: str, section_header: str, new_content: str, convert_markdown: bool = True) -> dict:
    """
    Replace an entire section by its header text.

    Finds a section by its header (h2 or h3), and replaces everything from that
    header to the next header of equal or higher level with new_content.

    Args:
        doc_id: The document ID
        section_header: The header text to find (without # symbols)
        new_content: The new content for this section (markdown or HTML)
        convert_markdown: If True, convert new_content from markdown to HTML

    Returns:
        {"status": "success/error", "message": "..."}
    """
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT id, title, content FROM docs WHERE id = ?", (doc_id,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        return {"status": "error", "message": f"Doc {doc_id} not found"}

    doc = _row_to_dict(row)
    content = doc.get("content", "")

    # Pattern to find section headers (h2 or h3)
    header_pattern = re.compile(r'<(h[23])>([^<]*)</\1>', re.IGNORECASE)

    # Find all headers with their positions
    matches = list(header_pattern.finditer(content))

    # Find the target section
    target_match = None
    target_level = None
    for match in matches:
        header_text = match.group(2).strip()
        if header_text.lower() == section_header.lower():
            if target_match is not None:
                conn.close()
                return {"status": "error", "message": f"Ambiguous: Multiple sections found with header '{section_header}'"}
            target_match = match
            target_level = int(match.group(1)[1])  # Get level number from h2/h3

    if target_match is None:
        conn.close()
        return {"status": "error", "message": f"Section not found: No h2 or h3 header matching '{section_header}'"}

    # Find where this section ends (next header of same or higher level)
    section_start = target_match.start()
    section_end = len(content)  # Default to end of document

    for match in matches:
        if match.start() > target_match.start():
            match_level = int(match.group(1)[1])
            if match_level <= target_level:  # Same or higher level header
                section_end = match.start()
                break

    # Build the replacement
    header_tag = f"h{target_level}"
    html_content = markdown_to_html(new_content) if convert_markdown else new_content
    replacement = f"<{header_tag}>{section_header}</{header_tag}>\n{html_content}\n"

    # Perform the replacement
    new_doc_content = content[:section_start] + replacement + content[section_end:]
    word_count = _count_words(new_doc_content)
    now = datetime.now().isoformat()

    cursor.execute("""
        UPDATE docs SET content = ?, word_count = ?, updated_at = ?, last_action = ?
        WHERE id = ?
    """, (new_doc_content, word_count, now, 'content_update', doc_id))

    conn.commit()
    conn.close()

    return {
        "status": "success",
        "message": f"Replaced section '{section_header}' in doc '{doc['title']}'"
    }


def append_doc(doc_id: str, content: str, convert_markdown: bool = True) -> dict:
    """
    Append content to an existing document.

    Args:
        doc_id: The document ID
        content: Content to append (markdown or HTML)
        convert_markdown: If True, convert markdown to HTML (default True)

    Returns:
        {"status": "success/error", "message": "..."}
    """
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT id, title, content FROM docs WHERE id = ?", (doc_id,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        return {"status": "error", "message": f"Doc {doc_id} not found"}

    doc = _row_to_dict(row)

    # Convert markdown to HTML if needed
    html_content = markdown_to_html(content) if convert_markdown else content

    # Auto-lint appended content for AI writing patterns
    lint_result = lint(html_content)
    html_content = lint_result.get("fixed_text", html_content)
    lint_changes = lint_result.get("change_log", [])

    existing = doc.get("content", "")
    combined_content = existing + html_content

    # Extract meta_description if ---summary--- marker is present in combined content
    combined_content, meta_description = _extract_meta_description(combined_content)
    word_count = _count_words(combined_content)
    now = datetime.now().isoformat()

    cursor.execute("""
        UPDATE docs SET content = ?, meta_description = COALESCE(?, meta_description),
            word_count = ?, updated_at = ?, last_action = ?
        WHERE id = ?
    """, (combined_content, meta_description, word_count, now, 'content_update', doc_id))

    conn.commit()
    conn.close()

    result = {
        "status": "success",
        "message": f"Appended to doc '{doc['title']}'"
    }
    if lint_changes:
        result["lint_changes"] = lint_changes
    return result


def delete_doc(doc_id: str) -> dict:
    """
    Delete a document.

    Args:
        doc_id: The document ID to delete

    Returns:
        {"status": "success/error", "message": "..."}
    """
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT id, title FROM docs WHERE id = ?", (doc_id,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        return {"status": "error", "message": f"Doc {doc_id} not found"}

    title = row['title']

    # Delete links first (foreign key constraint)
    cursor.execute("DELETE FROM links WHERE source_id = ? OR target_id = ?", (doc_id, doc_id))
    cursor.execute("DELETE FROM docs WHERE id = ?", (doc_id,))

    conn.commit()
    conn.close()

    return {
        "status": "success",
        "message": f"Deleted doc '{title}'"
    }


def delete_collection(collection: str) -> dict:
    """
    Delete all documents in a collection.

    Args:
        collection: The collection name to delete

    Returns:
        {"status": "success/error", "deleted_count": N, "collection": "..."}
    """
    # Resolve the collection name
    resolved_collection = resolve_collection(collection)

    conn = get_db()
    cursor = conn.cursor()

    # Count docs in this collection
    cursor.execute("SELECT COUNT(*) FROM docs WHERE collection = ?", (resolved_collection,))
    count = cursor.fetchone()[0]

    if count == 0:
        conn.close()
        return {
            "status": "error",
            "message": f"No documents found in collection '{resolved_collection}'"
        }

    # Get doc IDs for link cleanup
    cursor.execute("SELECT id FROM docs WHERE collection = ?", (resolved_collection,))
    doc_ids = [row['id'] for row in cursor.fetchall()]

    # Delete links for these docs
    for doc_id in doc_ids:
        cursor.execute("DELETE FROM links WHERE source_id = ? OR target_id = ?", (doc_id, doc_id))

    # Delete all docs in the collection
    cursor.execute("DELETE FROM docs WHERE collection = ?", (resolved_collection,))

    conn.commit()
    conn.close()

    return {
        "status": "success",
        "deleted_count": count,
        "collection": resolved_collection
    }


def read_doc(doc_id: str) -> dict:
    """
    Get a document by ID.

    Args:
        doc_id: The document ID

    Returns:
        {"status": "success/error", "doc": {...}}
    """
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM docs WHERE id = ?", (doc_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return {"status": "error", "message": f"Doc {doc_id} not found"}

    doc = _row_to_dict(row)

    # Parse stitched_from if it's a JSON string
    if doc.get('stitched_from') and isinstance(doc['stitched_from'], str):
        try:
            doc['stitched_from'] = json.loads(doc['stitched_from'])
        except json.JSONDecodeError:
            pass

    return {
        "status": "success",
        "doc": doc
    }



def read_section(doc_id: str, section_header: str = None, section: int = None) -> dict:
    """
    Read a section from a document by h2 header text or section number.

    Finds the matching <h2> tag in the doc content and returns everything
    from that <h2> until the next <h2> (or end of document).

    Args:
        doc_id: The document ID
        section_header: The header text to find (without h2 tags) - optional
        section: 1-indexed section number (1 = first h2, 2 = second h2, etc.) - optional

    Either section_header or section must be provided. If both provided, section takes priority.

    Returns:
        {"status": "success", "section_html": "...", "section_text": "...", "header": "...", "section_number": N}
        or {"status": "error", "message": "..."}
    """
    # Validate params
    if section is None and section_header is None:
        return {"status": "error", "message": "Either section or section_header must be provided"}

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT id, title, content FROM docs WHERE id = ?", (doc_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return {"status": "error", "message": f"Doc {doc_id} not found"}

    doc = _row_to_dict(row)
    content = doc.get("content", "")

    # Pattern to find h2 headers
    header_pattern = re.compile(r'<h2>([^<]*)</h2>', re.IGNORECASE)

    # Find all h2 headers with their positions
    matches = list(header_pattern.finditer(content))

    if not matches:
        return {"status": "error", "message": "No h2 sections found in document"}

    # Find the target section
    target_match = None
    section_number = None

    if section is not None:
        # Section number provided (1-indexed)
        if not isinstance(section, int) or section < 1:
            return {"status": "error", "message": f"section must be a positive integer, got {section}"}
        if section > len(matches):
            return {"status": "error", "message": f"Section {section} not found. Document has {len(matches)} h2 sections."}
        target_match = matches[section - 1]  # Convert to 0-indexed
        section_number = section
    else:
        # Fall back to section_header string match
        for idx, match in enumerate(matches):
            header_text = match.group(1).strip()
            if header_text.lower() == section_header.lower():
                target_match = match
                section_number = idx + 1  # Convert to 1-indexed
                break

        if target_match is None:
            return {"status": "error", "message": f"Section not found: No h2 header matching '{section_header}'"}

    # Find where this section ends (next h2 or end of document)
    section_start = target_match.start()
    section_end = len(content)  # Default to end of document

    for match in matches:
        if match.start() > target_match.start():
            section_end = match.start()
            break

    # Extract the section HTML (including the header)
    section_html = content[section_start:section_end].strip()

    # Convert to plain text by stripping HTML tags
    section_text = re.sub(r'<[^>]+>', ' ', section_html)
    section_text = re.sub(r'\s+', ' ', section_text).strip()

    return {
        "status": "success",
        "header": target_match.group(1).strip(),
        "section_html": section_html,
        "section_text": section_text,
        "section_number": section_number,
        "total_sections": len(matches)
    }


def batch_read(doc_ids: list) -> dict:
    """
    Read multiple documents in one call.

    Args:
        doc_ids: List of document IDs to read

    Returns:
        {"status": "success", "docs": {doc_id: {...}, ...}, "found": N, "not_found": [...]}
    """
    if not isinstance(doc_ids, list):
        return {"status": "error", "message": f"doc_ids must be a list, got {type(doc_ids).__name__}"}

    if not doc_ids:
        return {"status": "error", "message": "No doc_ids provided"}

    conn = get_db()
    cursor = conn.cursor()

    docs = {}
    not_found = []

    for doc_id in doc_ids:
        if not isinstance(doc_id, str):
            not_found.append(str(doc_id))
            continue

        cursor.execute("SELECT * FROM docs WHERE id = ?", (doc_id,))
        row = cursor.fetchone()

        if row:
            doc = _row_to_dict(row)
            # Parse stitched_from if it's a JSON string
            if doc.get('stitched_from') and isinstance(doc['stitched_from'], str):
                try:
                    doc['stitched_from'] = json.loads(doc['stitched_from'])
                except json.JSONDecodeError:
                    pass
            docs[doc_id] = doc
        else:
            not_found.append(doc_id)

    conn.close()

    return {
        "status": "success",
        "docs": docs,
        "found": len(docs),
        "not_found": not_found
    }


def batch_create_docs(docs: list, collection: str = "Notes", convert_markdown: bool = True) -> dict:
    """
    Create multiple documents in a single transaction.

    Args:
        docs: Array of dicts with title and content keys (optional: uuid for mapping)
        collection: Collection name for all imported docs
        convert_markdown: If True, convert markdown to HTML (default True)

    Returns:
        {status, created_count, doc_ids: [{uuid: doc_id}], errors: [...]}
    """
    if not isinstance(docs, list):
        return {"status": "error", "message": f"docs must be a list, got {type(docs).__name__}"}

    if not docs:
        return {"status": "error", "message": "No docs provided"}

    now = datetime.now().isoformat()

    # Resolve collection to match existing collection names
    resolved_collection = resolve_collection(collection)

    created_count = 0
    doc_ids = []
    errors = []

    conn = get_db()
    cursor = conn.cursor()

    for i, doc_input in enumerate(docs):
        if not isinstance(doc_input, dict):
            errors.append({"index": i, "error": f"Item must be dict, got {type(doc_input).__name__}"})
            continue

        title = doc_input.get("title")
        content = doc_input.get("content", "")
        input_uuid = doc_input.get("uuid")  # Optional original UUID for mapping

        if not title:
            errors.append({"index": i, "error": "Missing title"})
            continue

        # Generate doc_id
        doc_id = f"doc_{uuid.uuid4().hex[:8]}"

        # Convert markdown to HTML if needed
        html_content = markdown_to_html(content) if convert_markdown else content

        # Auto-lint content for AI writing patterns
        lint_result = lint(html_content)
        html_content = lint_result.get("fixed_text", html_content)

        # Calculate word count
        word_count = _count_words(html_content)

        try:
            cursor.execute("""
                INSERT INTO docs (id, title, content, collection, word_count, created_at, updated_at, last_action)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (doc_id, title, html_content, resolved_collection, word_count, now, now, 'content_update'))

            created_count += 1
            doc_ids.append({"uuid": input_uuid, "doc_id": doc_id} if input_uuid else {"doc_id": doc_id})
        except sqlite3.Error as e:
            errors.append({"index": i, "error": str(e)})

    conn.commit()
    conn.close()

    # Trigger vector index update once (background)
    try:
        import subprocess
        subprocess.Popen(
            ["python3", os.path.join(BASE_DIR, "tools", "docs_vector_indexer.py"), "--build"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    except Exception:
        pass  # Vector indexing is non-critical

    result = {
        "status": "success",
        "created_count": created_count,
        "collection": resolved_collection,
        "doc_ids": doc_ids
    }

    if errors:
        result["errors"] = errors

    return result


def stitch_docs(doc_ids: list, new_title: str) -> dict:
    """
    Stitch multiple documents into a single new document.

    Reads each doc in order, concatenates their content with HR dividers,
    and creates a new document in Inbox.

    Args:
        doc_ids: List of document IDs to stitch together (in order)
        new_title: Title for the newly created document

    Returns:
        {"status": "success", "doc_id": "doc_xxx", "message": "...", "source_docs": [...]}
    """
    if not isinstance(doc_ids, list):
        return {"status": "error", "message": f"doc_ids must be a list, got {type(doc_ids).__name__}"}

    if not doc_ids:
        return {"status": "error", "message": "No doc_ids provided"}

    if not new_title or not isinstance(new_title, str):
        return {"status": "error", "message": "new_title is required and must be a string"}

    conn = get_db()
    cursor = conn.cursor()

    # Collect content from each doc in order
    stitched_content = []
    source_docs = []
    not_found = []

    for doc_id in doc_ids:
        if not isinstance(doc_id, str):
            not_found.append(str(doc_id))
            continue

        cursor.execute("SELECT id, title, content FROM docs WHERE id = ?", (doc_id,))
        row = cursor.fetchone()

        if row:
            doc = _row_to_dict(row)
            source_docs.append({"id": doc_id, "title": doc.get("title", "Untitled")})
            # Add section header with doc title and HR divider
            stitched_content.append(f"<h2>{doc.get('title', 'Untitled')}</h2>")
            stitched_content.append(doc.get("content", ""))
            stitched_content.append('<hr style="margin: 24px 0; border: none; border-top: 1px solid #333;">')
        else:
            not_found.append(doc_id)

    if not source_docs:
        conn.close()
        return {"status": "error", "message": f"No valid docs found. Not found: {not_found}"}

    # Remove trailing HR
    if stitched_content and stitched_content[-1].startswith("<hr"):
        stitched_content.pop()

    # Join all content
    final_content = "\n\n".join(stitched_content)

    # Create the new doc in Inbox
    new_doc_id = f"doc_{uuid.uuid4().hex[:8]}"
    now = datetime.now().isoformat()
    word_count = _count_words(final_content)
    stitched_from_json = json.dumps([d["id"] for d in source_docs])

    cursor.execute("""
        INSERT INTO docs (id, title, content, collection, word_count, created_at, updated_at, stitched_from)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (new_doc_id, new_title, final_content, "Inbox", word_count, now, now, stitched_from_json))

    conn.commit()
    conn.close()

    result = {
        "status": "success",
        "doc_id": new_doc_id,
        "message": f"Created stitched doc '{new_title}' in Inbox from {len(source_docs)} docs",
        "source_docs": source_docs
    }

    if not_found:
        result["not_found"] = not_found

    return result


def search_within_doc(doc_id: str, query: str) -> dict:
    """
    Search within a specific document's content.

    Args:
        doc_id: The document ID to search within
        query: Search term to find (case-insensitive)

    Returns:
        {"status": "success", "doc_id": "...", "query": "...", "matches": [...], "match_count": N}
    """
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT id, title, content FROM docs WHERE id = ?", (doc_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return {"status": "error", "message": f"Doc {doc_id} not found"}

    doc = _row_to_dict(row)
    content = doc.get("content", "")

    # Strip HTML tags for clean text matching
    clean_text = re.sub(r'<[^>]+>', ' ', content)
    # Normalize whitespace
    clean_text = re.sub(r'\s+', ' ', clean_text).strip()

    # Case-insensitive search
    query_lower = query.lower()
    text_lower = clean_text.lower()

    matches = []
    position = 0

    while True:
        pos = text_lower.find(query_lower, position)
        if pos == -1:
            break

        # Extract surrounding context (sentence or paragraph snippet)
        # Get ~100 chars before and after
        start = max(0, pos - 100)
        end = min(len(clean_text), pos + len(query) + 100)

        # Adjust start to not cut words
        if start > 0:
            space_pos = clean_text.find(' ', start)
            if space_pos != -1 and space_pos < pos:
                start = space_pos + 1

        # Adjust end to not cut words
        if end < len(clean_text):
            space_pos = clean_text.rfind(' ', pos + len(query), end)
            if space_pos != -1:
                end = space_pos

        snippet = clean_text[start:end].strip()
        if start > 0:
            snippet = "..." + snippet
        if end < len(clean_text):
            snippet = snippet + "..."

        matches.append({
            "text": snippet,
            "position": pos
        })

        position = pos + len(query)

    return {
        "status": "success",
        "doc_id": doc_id,
        "doc_title": doc.get("title", "Untitled"),
        "query": query,
        "matches": matches,
        "match_count": len(matches)
    }


def list_docs(collection: str = None, min_words: int = None, max_words: int = None) -> dict:
    """
    List all documents, optionally filtered by collection and word count.

    Args:
        collection: Filter by collection name (optional)
        min_words: Only return docs with word_count >= this value (optional)
        max_words: Only return docs with word_count <= this value (optional)

    Returns:
        {"status": "success", "docs": [...]}
    """
    conn = get_db()
    cursor = conn.cursor()

    # Build query
    query = "SELECT id, title, collection, updated_at, word_count, last_action FROM docs WHERE 1=1"
    params = []

    # Resolve collection name if provided
    if collection:
        resolved_collection = resolve_collection(collection)
        query += " AND collection = ?"
        params.append(resolved_collection)

    if min_words is not None:
        query += " AND word_count >= ?"
        params.append(min_words)

    if max_words is not None:
        query += " AND word_count <= ?"
        params.append(max_words)

    query += " ORDER BY LOWER(title)"

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    docs_list = []
    for row in rows:
        docs_list.append({
            "id": row['id'],
            "title": row['title'],
            "collection": row['collection'],
            "updated_at": row['updated_at'],
            "word_count": row['word_count'],
            "last_action": row['last_action'] or 'content_update'
        })

    return {
        "status": "success",
        "count": len(docs_list),
        "docs": docs_list
    }


def _get_whoosh_schema():
    """Define Whoosh schema with weighted fields."""
    analyzer = StemmingAnalyzer()
    return Schema(
        doc_id=ID(stored=True, unique=True),
        title=TEXT(analyzer=analyzer, stored=True, field_boost=5.0),
        meta_description=TEXT(analyzer=analyzer, field_boost=3.0),
        content=TEXT(analyzer=analyzer, field_boost=1.0),
        collection=TEXT(stored=True),
        updated_at=TEXT(stored=True),
        link_count=NUMERIC(stored=True)
    )


def _get_db_mtime():
    """Get modification time of docs.db."""
    try:
        return os.path.getmtime(DB_PATH)
    except OSError:
        return 0


def _needs_reindex():
    """Check if index needs rebuilding based on docs.db modification time.
    Uses file-based mtime marker because subprocess resets in-memory state."""
    # No index exists
    if not os.path.exists(WHOOSH_INDEX_DIR):
        return True

    # Check if index is valid
    if not index.exists_in(WHOOSH_INDEX_DIR):
        return True

    # Compare docs.db mtime against last build marker
    current_mtime = _get_db_mtime()
    if os.path.exists(INDEX_MTIME_MARKER):
        try:
            with open(INDEX_MTIME_MARKER, 'r') as f:
                last_build_mtime = float(f.read().strip())
            if current_mtime <= last_build_mtime:
                return False  # Index is current
        except (ValueError, OSError):
            pass

    return True


def build_whoosh_index(force: bool = False) -> dict:
    """
    Build or rebuild the Whoosh search index from docs.db.

    Args:
        force: If True, rebuild even if index appears current

    Returns:
        {"status": "success", "indexed": N} or {"status": "error", "error": "..."}
    """
    global _last_index_mtime

    if not force and not _needs_reindex():
        return {"status": "success", "message": "Index is current", "indexed": 0}

    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT id, title, meta_description, content, collection, updated_at FROM docs")
        rows = cursor.fetchall()
        conn.close()

        # Create index directory if needed
        if not os.path.exists(WHOOSH_INDEX_DIR):
            os.makedirs(WHOOSH_INDEX_DIR)

        # Create fresh index
        schema = _get_whoosh_schema()
        ix = index.create_in(WHOOSH_INDEX_DIR, schema)

        writer = ix.writer()
        indexed_count = 0

        # Get link counts from links table
        conn = get_db()
        cursor = conn.cursor()
        link_counts = {}
        cursor.execute("SELECT target_id, COUNT(*) as cnt FROM links GROUP BY target_id")
        for row in cursor.fetchall():
            link_counts[row['target_id']] = row['cnt']
        conn.close()

        for row in rows:
            doc = _row_to_dict(row)
            doc_id = doc['id']
            title = doc.get("title", "")
            meta_desc = doc.get("meta_description", "")

            # Strip HTML tags from content
            raw_content = doc.get("content", "")
            content = re.sub(r'<[^>]+>', ' ', raw_content)

            # Get link count for this doc
            link_count = link_counts.get(doc_id, 0)

            writer.add_document(
                doc_id=doc_id,
                title=title,
                meta_description=meta_desc,
                content=content,
                collection=doc.get("collection", "Notes"),
                updated_at=doc.get("updated_at", ""),
                link_count=link_count
            )
            indexed_count += 1

        writer.commit()

        # Write file-based mtime marker so subprocesses know index is current
        build_mtime = _get_db_mtime()
        with open(INDEX_MTIME_MARKER, 'w') as f:
            f.write(str(build_mtime))

        return {
            "status": "success",
            "indexed": indexed_count,
            "index_path": WHOOSH_INDEX_DIR
        }

    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }


def preprocess_query(q):
    """Normalize query: split camelCase, replace underscores/hyphens with spaces, lowercase."""
    import re
    # Split camelCase: 'riskBased' to 'risk Based'
    q = re.sub(r'([a-z])([A-Z])', r'\1 \2', q)
    # Replace underscores/hyphens with spaces
    q = re.sub(r'[-_]', ' ', q)
    return q.lower()


def search_docs(query = "", max_results: int = 15, status: str = None, has_field: str = None, collection: str = None, min_words: int = None, max_words: int = None) -> dict:
    """
    Search documents using Whoosh BM25 ranked search, or filter-only mode.

    Uses weighted fields: title (5x), meta_description (3x), link_count (2x), content (1x).
    Requires ALL query tokens to match (AND logic).
    Uses word boundary matching, not substring.
    Title-only matches rank highest.

    Filter-only mode: When query is empty but filters (status, has_field, collection, min_words, max_words) are provided,
    returns all matching docs sorted by updated_at descending without scoring.

    Batch mode: When query is a list of strings, returns results for all queries.

    Args:
        query: Search query string OR list of query strings (batch mode)
        max_results: Maximum number of results to return per query (default 15)
        status: Optional filter - only return docs with matching status
        has_field: Optional filter - only return docs where this field exists and is non-empty
        collection: Optional filter - only return docs in this collection
        min_words: Optional filter - only return docs with word_count >= this value
        max_words: Optional filter - only return docs with word_count <= this value

    Returns:
        Single query: {"status": "success", "query": "...", "count": N, "docs": [...]}
        Batch query: {"status": "success", "results": {"query1": [...], ...}, "queries_processed": N}
    """
    # Handle array input - delegate to batch_search
    if isinstance(query, list):
        return batch_search(query=query, collection=collection, limit=max_results)

    # Preprocess query: normalize camelCase, underscores, hyphens
    query = preprocess_query(query)

    # Resolve collection name if provided
    if collection:
        collection = resolve_collection(collection)

    query = query or ""
    has_filters = status or has_field or collection or min_words is not None or max_words is not None

    # Filter-only mode: no query but has filters
    if not query.strip() and has_filters:
        conn = get_db()
        cursor = conn.cursor()

        # Build dynamic query based on filters
        sql = "SELECT id, title, collection, updated_at, word_count, status, published_url, description, campaign_id FROM docs WHERE 1=1"
        params = []

        if status:
            sql += " AND status = ?"
            params.append(status)
        if collection:
            sql += " AND collection = ?"
            params.append(collection)
        if min_words is not None:
            sql += " AND word_count >= ?"
            params.append(min_words)
        if max_words is not None:
            sql += " AND word_count <= ?"
            params.append(max_words)
        if has_field:
            sql += f" AND {has_field} IS NOT NULL AND {has_field} != ''"

        sql += " ORDER BY updated_at DESC LIMIT ?"
        params.append(max_results)

        cursor.execute(sql, params)
        rows = cursor.fetchall()
        conn.close()

        matches = []
        for row in rows:
            doc = _row_to_dict(row)
            result = {
                "id": doc['id'],
                "title": doc['title'],
                "collection": doc['collection'],
                "updated_at": doc['updated_at'],
                "word_count": doc['word_count'],
                "score": 0  # No scoring in filter-only mode
            }

            # Add metadata fields if they exist
            if doc.get("status"):
                result["status"] = doc["status"]
            if doc.get("published_url"):
                result["published_url"] = doc["published_url"]
            if doc.get("description"):
                result["description"] = doc["description"]
            if doc.get("campaign_id"):
                result["campaign_id"] = doc["campaign_id"]

            matches.append(result)

        return {
            "status": "success",
            "query": query,
            "count": len(matches),
            "docs": matches,
            "mode": "filter_only"
        }

    # No query and no filters - return empty
    if not query.strip():
        return {
            "status": "success",
            "query": query,
            "count": 0,
            "docs": []
        }

    # Ensure index is current
    if _needs_reindex():
        build_result = build_whoosh_index()
        if build_result.get("status") == "error":
            return {
                "status": "error",
                "query": query,
                "error": f"Index build failed: {build_result.get('error')}"
            }

    # Load metadata from SQLite for filtering
    conn = get_db()
    cursor = conn.cursor()

    # Pre-filter doc IDs based on status, has_field, collection, and word count
    sql = "SELECT id, title, collection, updated_at, word_count, status, published_url, description, campaign_id FROM docs WHERE 1=1"
    params = []

    if status:
        sql += " AND status = ?"
        params.append(status)
    if collection:
        sql += " AND collection = ?"
        params.append(collection)
    if min_words is not None:
        sql += " AND word_count >= ?"
        params.append(min_words)
    if max_words is not None:
        sql += " AND word_count <= ?"
        params.append(max_words)
    if has_field:
        sql += f" AND {has_field} IS NOT NULL AND {has_field} != ''"

    cursor.execute(sql, params)
    rows = cursor.fetchall()
    conn.close()

    filtered_doc_ids = set()
    all_docs = {}
    doc_word_counts = {}

    for row in rows:
        doc = _row_to_dict(row)
        filtered_doc_ids.add(doc['id'])
        all_docs[doc['id']] = doc
        doc_word_counts[doc['id']] = doc['word_count']

    try:
        ix = index.open_dir(WHOOSH_INDEX_DIR)

        # Parse query with AND logic across multiple fields
        parser = MultifieldParser(
            ["title", "meta_description", "content"],
            schema=ix.schema,
            group=AndGroup  # Require ALL terms
        )

        parsed_query = parser.parse(query)

        semantic_matches = []
        whoosh_matches = []
        existing_ids = set()

        # STEP 1: Semantic search FIRST (primary ranking)
        if query.strip():
            try:
                semantic_fn = _get_semantic_search()
                sem_result = semantic_fn(
                    query=query,
                    top_k=max_results,
                    collection=collection  # Pass through collection filter
                )
                if sem_result.get("status") == "success":
                    for sr in sem_result.get("results", []):
                        # Post-filter semantic results through same filters as Whoosh
                        doc = all_docs.get(sr["doc_id"], {})
                        if not doc:
                            # Need to fetch from DB
                            conn = get_db()
                            cursor = conn.cursor()
                            cursor.execute("SELECT * FROM docs WHERE id = ?", (sr["doc_id"],))
                            row = cursor.fetchone()
                            conn.close()
                            if row:
                                doc = _row_to_dict(row)
                            else:
                                continue

                        # Apply status filter
                        if status and doc.get("status") != status:
                            continue
                        # Apply has_field filter
                        if has_field and not doc.get(has_field):
                            continue
                        # Calculate word count and apply filters
                        word_count = doc.get("word_count", 0)
                        if min_words is not None and word_count < min_words:
                            continue
                        if max_words is not None and word_count > max_words:
                            continue

                        # Convert semantic result format to search_docs format
                        result = {
                            "id": sr["doc_id"],
                            "title": sr["title"],
                            "collection": sr["collection"],
                            "updated_at": doc.get("updated_at", ""),
                            "word_count": word_count,
                            "score": 0,  # No BM25 score
                            "semantic_similarity": round(sr["similarity"], 3),
                            "source": "semantic"
                        }

                        # Add metadata fields if they exist
                        if doc.get("status"):
                            result["status"] = doc["status"]
                        if doc.get("published_url"):
                            result["published_url"] = doc["published_url"]
                        if doc.get("description"):
                            result["description"] = doc["description"]
                        if doc.get("campaign_id"):
                            result["campaign_id"] = doc["campaign_id"]

                        semantic_matches.append(result)
                        existing_ids.add(sr["doc_id"])

            except Exception as e:
                logging.warning(f"Semantic search failed silently: {e}")

        # STEP 2: Whoosh BM25 search SECOND (fills gaps)
        with ix.searcher(weighting=scoring.BM25F()) as searcher:
            results = searcher.search(parsed_query, limit=max_results * 3)  # Over-fetch to account for filtering

            for hit in results:
                doc_id = hit["doc_id"]

                # Skip if already in semantic results (semantic takes priority)
                if doc_id in existing_ids:
                    continue

                # Skip if doc was filtered out
                if filtered_doc_ids and doc_id not in filtered_doc_ids:
                    continue

                # Boost title-only matches
                title_boost = 0
                title_lower = hit["title"].lower()
                query_tokens = query.lower().split()
                if all(token in title_lower for token in query_tokens):
                    title_boost = 10.0

                # Get metadata from original doc
                doc = all_docs.get(doc_id, {})
                result = {
                    "id": doc_id,
                    "title": hit["title"],
                    "collection": hit["collection"],
                    "updated_at": hit["updated_at"],
                    "word_count": doc_word_counts.get(doc_id, doc.get("word_count", 0)),
                    "score": round(hit.score + title_boost, 2),
                    "source": "whoosh"
                }

                # Add metadata fields if they exist
                if doc.get("status"):
                    result["status"] = doc["status"]
                if doc.get("published_url"):
                    result["published_url"] = doc["published_url"]
                if doc.get("description"):
                    result["description"] = doc["description"]
                if doc.get("campaign_id"):
                    result["campaign_id"] = doc["campaign_id"]

                whoosh_matches.append(result)
                existing_ids.add(doc_id)

        # Sort whoosh matches by BM25 score
        whoosh_matches.sort(key=lambda x: x["score"], reverse=True)

        # STEP 3: Merge - semantic results first (ranked by similarity), then whoosh results
        # Semantic matches already ordered by similarity from the vector search
        matches = semantic_matches + whoosh_matches

        # Truncate to max_results
        matches = matches[:max_results]

        return {
            "status": "success",
            "query": query,
            "count": len(matches),
            "docs": matches
        }

    except Exception as e:
        return {
            "status": "error",
            "query": query,
            "error": str(e)
        }


def batch_search(query, collection: str = None, limit: int = 5) -> dict:
    """
    Search documents with single or multiple queries. Unified interface.

    Args:
        query: Search query - either a string (single search) or list of strings (batch)
        collection: Optional filter - only search docs in this collection
        limit: Maximum results per query (default 5)

    Returns:
        {"status": "success", "results": {"query1": [...docs], ...}, "queries_processed": N}
    """
    # Normalize input: wrap string in list
    if isinstance(query, str):
        queries = [query]
    elif isinstance(query, list):
        queries = query
    else:
        return {
            "status": "error",
            "message": f"query must be string or list, got {type(query).__name__}"
        }

    # Validate queries
    queries = [q for q in queries if q and isinstance(q, str) and q.strip()]
    if not queries:
        return {
            "status": "error",
            "message": "No valid queries provided"
        }

    # Resolve collection name if provided
    if collection:
        collection = resolve_collection(collection)

    # Ensure index is current
    if _needs_reindex():
        build_result = build_whoosh_index()
        if build_result.get("status") == "error":
            return {
                "status": "error",
                "message": f"Index build failed: {build_result.get('error')}"
            }

    # Load metadata from SQLite
    conn = get_db()
    cursor = conn.cursor()

    if collection:
        cursor.execute("SELECT id, title, collection, updated_at, status, published_url, description FROM docs WHERE collection = ?", (collection,))
    else:
        cursor.execute("SELECT id, title, collection, updated_at, status, published_url, description FROM docs")

    rows = cursor.fetchall()
    conn.close()

    all_docs = {}
    filtered_doc_ids = set()
    for row in rows:
        doc = _row_to_dict(row)
        all_docs[doc['id']] = doc
        filtered_doc_ids.add(doc['id'])

    results = {}

    try:
        ix = index.open_dir(WHOOSH_INDEX_DIR)

        with ix.searcher(weighting=scoring.BM25F()) as searcher:
            for query_str in queries:
                # Parse query with AND logic
                parser = MultifieldParser(
                    ["title", "meta_description", "content"],
                    schema=ix.schema,
                    group=AndGroup
                )

                parsed_query = parser.parse(query_str)
                search_results = searcher.search(parsed_query, limit=limit * 3)

                query_matches = []
                for hit in search_results:
                    doc_id = hit["doc_id"]

                    # Skip if doc was filtered out by collection
                    if filtered_doc_ids and doc_id not in filtered_doc_ids:
                        continue

                    # Stop if we have enough results for this query
                    if len(query_matches) >= limit:
                        break

                    # Boost title-only matches
                    title_boost = 0
                    title_lower = hit["title"].lower()
                    query_tokens = query_str.lower().split()
                    if all(token in title_lower for token in query_tokens):
                        title_boost = 10.0

                    # Get metadata from original doc
                    doc = all_docs.get(doc_id, {})
                    result = {
                        "id": doc_id,
                        "title": hit["title"],
                        "collection": hit["collection"],
                        "updated_at": hit["updated_at"],
                        "score": round(hit.score + title_boost, 2)
                    }

                    # Add metadata fields if they exist
                    if doc.get("status"):
                        result["status"] = doc["status"]
                    if doc.get("published_url"):
                        result["published_url"] = doc["published_url"]
                    if doc.get("description"):
                        result["description"] = doc["description"]

                    query_matches.append(result)

                # Sort by score descending
                query_matches.sort(key=lambda x: x["score"], reverse=True)
                results[query_str] = query_matches

        response = {
            "status": "success",
            "results": results,
            "queries_processed": len(queries)
        }

        if collection:
            response["collection_filter"] = collection

        return response

    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }


def import_docs(directory: str, default_collection: str = "Imported") -> dict:
    """
    Import markdown files from a directory into doc_editor.

    Outline export structure: collection_name/doc_title.md
    Title comes from filename, collection from parent folder.

    Args:
        directory: Path to directory containing markdown files (Outline export)
        default_collection: Collection name if no parent folder (default: Imported)

    Returns:
        {"status": "success", "imported": N, "failed": N, "details": [...]}
    """
    from pathlib import Path

    now = datetime.now().isoformat()

    results = {
        "imported": 0,
        "failed": 0,
        "skipped": 0,
        "details": []
    }

    base_path = Path(directory)
    if not base_path.exists():
        return {"status": "error", "message": f"Directory not found: {directory}"}

    # Find all markdown files recursively
    md_files = list(base_path.rglob("*.md"))

    conn = get_db()
    cursor = conn.cursor()

    for md_file in md_files:
        try:
            # Get collection from parent folder name (if exists and not the base dir)
            rel_path = md_file.relative_to(base_path)
            if len(rel_path.parts) > 1:
                collection = rel_path.parts[0]
            else:
                collection = default_collection

            # Resolve collection name to match existing collections
            collection = resolve_collection(collection)

            # Get title from filename (without .md)
            title = md_file.stem

            # Read content
            content = md_file.read_text(encoding='utf-8')

            # Generate doc ID
            doc_id = f"doc_{uuid.uuid4().hex[:8]}"

            # Convert markdown to HTML
            html_content = markdown_to_html(content)
            word_count = _count_words(html_content)

            # Store doc
            cursor.execute("""
                INSERT INTO docs (id, title, content, collection, word_count, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (doc_id, title, html_content, collection, word_count, now, now))

            results["imported"] += 1
            results["details"].append({
                "title": title,
                "collection": collection,
                "doc_id": doc_id
            })

        except Exception as e:
            results["failed"] += 1
            results["details"].append({
                "file": str(md_file),
                "error": str(e)
            })

    conn.commit()
    conn.close()

    return {
        "status": "success",
        "message": f"Imported {results['imported']} docs, {results['failed']} failed",
        **results
    }


def update_metadata(doc_id: str, status: str = None, description: str = None,
                    campaign_id: str = None, published_url: str = None) -> dict:
    """
    Update ONLY metadata fields on a document. DOES NOT touch content.

    Args:
        doc_id: The document ID to update
        status: New status (optional, e.g., 'draft', 'published', 'archived')
        description: Short description (optional)
        campaign_id: Associated campaign ID (optional)
        published_url: URL where doc was published (optional)

    Returns:
        {"status": "success/error", "message": "...", "updated_fields": [...]}
    """
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT id, title, collection FROM docs WHERE id = ?", (doc_id,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        return {"status": "error", "message": f"Doc {doc_id} not found"}

    doc = _row_to_dict(row)
    updated_fields = []
    updates = []
    params = []

    # Only update fields that were explicitly provided (non-None)
    if status is not None:
        updates.append("status = ?")
        params.append(status)
        updated_fields.append("status")

    if description is not None:
        updates.append("description = ?")
        params.append(description)
        updated_fields.append("description")

    if campaign_id is not None:
        updates.append("campaign_id = ?")
        params.append(campaign_id)
        updated_fields.append("campaign_id")

    if published_url is not None:
        updates.append("published_url = ?")
        params.append(published_url)
        updated_fields.append("published_url")

    if not updated_fields:
        conn.close()
        return {"status": "error", "message": "No fields provided to update"}

    updates.append("updated_at = ?")
    params.append(datetime.now().isoformat())
    updates.append("last_action = ?")
    params.append("update_metadata")

    params.append(doc_id)

    cursor.execute(f"UPDATE docs SET {', '.join(updates)} WHERE id = ?", params)
    conn.commit()
    conn.close()

    # Auto-sync content calendar for content collections
    collection = doc.get("collection", "").lower()
    if collection in ['blogs', 'video', 'newsletters']:
        sync_content_calendar()

    return {
        "status": "success",
        "message": f"Updated metadata for doc '{doc['title']}': {', '.join(updated_fields)}",
        "updated_fields": updated_fields
    }


def batch_update_metadata(updates: list) -> dict:
    """
    Update metadata on multiple documents in one call.

    Args:
        updates: List of update objects, each containing:
            - doc_id: Required document ID
            - metadata: Object with fields to update (description, tags, doc_type, status, etc.)

    Returns:
        {"status": "success", "success_count": N, "failed": [...], "results": [...]}
    """
    if not isinstance(updates, list):
        return {"status": "error", "message": f"updates must be a list, got {type(updates).__name__}"}

    if not updates:
        return {"status": "error", "message": "No updates provided"}

    conn = get_db()
    cursor = conn.cursor()

    success_count = 0
    failed = []
    results = []
    collections_to_sync = set()
    now = datetime.now().isoformat()

    for update in updates:
        if not isinstance(update, dict):
            failed.append({"error": f"Invalid update format: {update}"})
            continue

        doc_id = update.get("doc_id")
        if not doc_id:
            failed.append({"error": "Missing doc_id", "update": update})
            continue

        cursor.execute("SELECT id, title, collection FROM docs WHERE id = ?", (doc_id,))
        row = cursor.fetchone()

        if not row:
            failed.append({"doc_id": doc_id, "error": "Document not found"})
            continue

        doc = _row_to_dict(row)

        metadata = update.get("metadata", {})
        if not isinstance(metadata, dict) or not metadata:
            failed.append({"doc_id": doc_id, "error": "Missing or invalid metadata"})
            continue

        updated_fields = []
        update_parts = []
        params = []

        # Update each provided metadata field
        for field, value in metadata.items():
            if value is not None:
                update_parts.append(f"{field} = ?")
                params.append(value)
                updated_fields.append(field)

        if updated_fields:
            update_parts.append("updated_at = ?")
            params.append(now)
            params.append(doc_id)

            cursor.execute(f"UPDATE docs SET {', '.join(update_parts)} WHERE id = ?", params)

            success_count += 1
            results.append({
                "doc_id": doc_id,
                "title": doc['title'],
                "updated_fields": updated_fields
            })

            # Track collections that may need content calendar sync
            collection = doc.get("collection", "").lower()
            if collection in ['blogs', 'video', 'newsletters']:
                collections_to_sync.add(collection)
        else:
            failed.append({"doc_id": doc_id, "error": "No valid fields to update"})

    conn.commit()
    conn.close()

    # Sync content calendar if any content collections were updated
    if collections_to_sync:
        sync_content_calendar()

    return {
        "status": "success",
        "success_count": success_count,
        "failed": failed,
        "results": results
    }


def migrate_from_outline(exclude_collections: list = None) -> dict:
    """
    Migrate ALL docs from Outline to doc_editor via direct Postgres query.

    One SQL query, one file write. No API calls.

    Args:
        exclude_collections: List of collection names to skip (optional)

    Returns:
        {"status": "success", "imported": N, "collections": {...}}
    """
    import psycopg2

    exclude = exclude_collections or []

    try:
        pg_conn = psycopg2.connect(
            host='localhost',
            port=5432,
            database='outline',
            user='user',
            password='pass'
        )
    except Exception as e:
        return {"status": "error", "message": f"DB connection failed: {e}"}

    try:
        pg_cur = pg_conn.cursor()

        # Get all docs with their collection names in one query
        pg_cur.execute("""
            SELECT
                d.id,
                d.title,
                d.text,
                c.name as collection_name,
                d."createdAt",
                d."updatedAt"
            FROM documents d
            JOIN collections c ON d."collectionId" = c.id
            WHERE d."deletedAt" IS NULL
              AND d."archivedAt" IS NULL
            ORDER BY c.name, d.title
        """)

        rows = pg_cur.fetchall()
        pg_cur.close()
        pg_conn.close()

    except Exception as e:
        pg_conn.close()
        return {"status": "error", "message": f"Query failed: {e}"}

    # Open SQLite connection
    conn = get_db()
    cursor = conn.cursor()
    now = datetime.now().isoformat()

    results = {
        "imported": 0,
        "skipped": 0,
        "collections": {}
    }

    for row in rows:
        outline_id, title, content, collection, created_at, updated_at = row

        # Skip excluded collections
        if collection in exclude:
            results["skipped"] += 1
            continue

        # Generate new doc ID
        doc_id = f"doc_{uuid.uuid4().hex[:8]}"

        # Convert markdown to HTML
        html_content = markdown_to_html(content or "")
        word_count = _count_words(html_content)

        # Store doc
        cursor.execute("""
            INSERT INTO docs (id, title, content, collection, word_count, created_at, updated_at, outline_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            doc_id, title, html_content, collection, word_count,
            created_at.isoformat() if created_at else now,
            updated_at.isoformat() if updated_at else now,
            str(outline_id)
        ))

        results["imported"] += 1
        results["collections"][collection] = results["collections"].get(collection, 0) + 1

    conn.commit()
    conn.close()

    return {
        "status": "success",
        "message": f"Migrated {results['imported']} docs from Outline",
        **results
    }


def retrieve_doc(title: str, collection: str = None) -> dict:
    """
    Retrieve a document by title (search + get in one call).

    Searches docs using tokenized matching, optionally filters by collection,
    takes the top result, and returns the full document content.

    Args:
        title: Title to search for
        collection: Optional collection filter

    Returns:
        {"status": "success/error", "doc": {...}} or {"status": "error", "message": "..."}
    """
    # Resolve collection name if provided
    if collection:
        collection = resolve_collection(collection)

    # Search for matching docs
    search_result = search_docs(title)

    if search_result.get("status") != "success" or search_result.get("count", 0) == 0:
        return {"status": "error", "message": f"No doc found matching title: {title}"}

    matches = search_result.get("docs", [])

    # Filter by collection if specified
    if collection:
        matches = [m for m in matches if m.get("collection") == collection]
        if not matches:
            return {"status": "error", "message": f"No doc found matching title '{title}' in collection '{collection}'"}

    # Get top result
    top_match = matches[0]

    # Fetch full document
    return read_doc(top_match["id"])


def sync_content_calendar() -> dict:
    """
    Sync docs from Blogs, Video, Newsletters collections to content_calendar.json.
    Mirrors outline_editor.get_content_calendar but reads from SQLite docs.db.
    """
    conn = get_db()
    cursor = conn.cursor()

    # Map collection names to content types (case-insensitive matching)
    collection_map = {
        'blogs': 'blog',
        'video': 'video',
        'newsletters': 'newsletter'
    }

    entries = {}
    counts = {'blog': 0, 'video': 0, 'newsletter': 0}

    cursor.execute("""
        SELECT id, title, description, status, published_url, campaign_id, collection
        FROM docs
        WHERE LOWER(collection) IN ('blogs', 'video', 'newsletters')
    """)

    for row in cursor.fetchall():
        doc = _row_to_dict(row)
        collection = doc.get("collection", "").lower()

        if collection in collection_map:
            content_type = collection_map[collection]
            entries[doc['id']] = {
                'doc_id': doc['id'],
                'title': doc.get('title', ''),
                'description': doc.get('description', ''),
                'status': doc.get('status'),
                'url': doc.get('published_url'),
                'campaign_id': doc.get('campaign_id'),
                'type': content_type
            }
            counts[content_type] += 1

    conn.close()

    result = {
        'last_synced': datetime.now().isoformat(),
        'entries': entries
    }

    # Write to content_calendar.json
    output_path = os.path.join(BASE_DIR, 'semantic_memory', 'content_calendar.json')
    with open(output_path, 'w') as f:
        json.dump(result, f, indent=2)

    return {
        'status': 'success',
        'message': f'Synced content calendar: {counts["blog"]} blogs, {counts["video"]} videos, {counts["newsletter"]} newsletters',
        'output_path': output_path,
        'counts': counts
    }


def list_revisions(doc_id: str) -> dict:
    """List all revisions for a document.

    Args:
        doc_id: The document ID

    Returns:
        {"status": "success", "revisions": [...]} or {"status": "error", "message": "..."}
    """
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM docs WHERE id = ?", (doc_id,))
    if not cursor.fetchone():
        conn.close()
        return {"status": "error", "message": f"Doc {doc_id} not found"}

    cursor.execute(
        "SELECT revision_number, created_at FROM revisions WHERE doc_id = ? ORDER BY revision_number DESC",
        (doc_id,)
    )
    rows = cursor.fetchall()
    conn.close()

    revisions = [{"revision": row[0], "created_at": row[1]} for row in rows]
    return {"status": "success", "doc_id": doc_id, "count": len(revisions), "revisions": revisions}


def get_revision(doc_id: str, revision: int) -> dict:
    """Get the content of a specific revision.

    Args:
        doc_id: The document ID
        revision: The revision number to retrieve

    Returns:
        {"status": "success", "content": "..."} or {"status": "error", "message": "..."}
    """
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT content, created_at FROM revisions WHERE doc_id = ? AND revision_number = ?",
        (doc_id, revision)
    )
    row = cursor.fetchone()
    conn.close()

    if not row:
        return {"status": "error", "message": f"Revision {revision} not found for doc {doc_id}"}

    return {"status": "success", "doc_id": doc_id, "revision": revision, "content": row[0], "created_at": row[1]}


def restore_revision(doc_id: str, revision: int) -> dict:
    """Restore a document to a specific revision.

    Snapshots the current content first, then restores the specified revision.

    Args:
        doc_id: The document ID
        revision: The revision number to restore

    Returns:
        {"status": "success", "message": "..."} or {"status": "error", "message": "..."}
    """
    conn = get_db()
    cursor = conn.cursor()

    # Get current content
    cursor.execute("SELECT id, title, content FROM docs WHERE id = ?", (doc_id,))
    doc_row = cursor.fetchone()
    if not doc_row:
        conn.close()
        return {"status": "error", "message": f"Doc {doc_id} not found"}

    current_content = doc_row[2]
    doc_title = doc_row[1]

    # Get the revision to restore
    cursor.execute(
        "SELECT content FROM revisions WHERE doc_id = ? AND revision_number = ?",
        (doc_id, revision)
    )
    rev_row = cursor.fetchone()
    if not rev_row:
        conn.close()
        return {"status": "error", "message": f"Revision {revision} not found for doc {doc_id}"}

    restored_content = rev_row[0]

    # Snapshot current content before restoring
    new_rev = _snapshot_revision(conn, doc_id, current_content)

    # Update doc with restored content
    now = datetime.now().isoformat()
    word_count = _count_words(restored_content)
    cursor.execute(
        "UPDATE docs SET content = ?, word_count = ?, updated_at = ?, last_action = ? WHERE id = ?",
        (restored_content, word_count, now, 'revision_restore', doc_id)
    )
    conn.commit()
    conn.close()

    return {
        "status": "success",
        "message": f"Restored '{doc_title}' to revision {revision}. Current content saved as revision {new_rev}."
    }


# CLI dispatcher
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print(json.dumps({"status": "error", "message": "No action specified"}))
        sys.exit(1)

    action = sys.argv[1]

    # Parse --params JSON
    params = {}
    for i, arg in enumerate(sys.argv):
        if arg == "--params" and i + 1 < len(sys.argv):
            params = json.loads(sys.argv[i + 1])
            break

    # Flatten nested params wrapper if present
    # Supports both: {"query": "x"} and {"params": {"query": "x"}}
    if "params" in params and isinstance(params["params"], dict):
        params = params["params"]

    # Import verify_backfill from separate module
    from verify_backfill import verify_backfill

    actions = {
        "create_doc": create_doc,
        "batch_create_docs": batch_create_docs,
        "update_doc": update_doc,
        "update_metadata": update_metadata,
        "batch_update_metadata": batch_update_metadata,
        "replace_section": replace_section,
        "append_doc": append_doc,
        "delete_doc": delete_doc,
        "delete_collection": delete_collection,
        "read_doc": read_doc,
        "read_section": read_section,
        "batch_read": batch_read,
        "search_within_doc": search_within_doc,
        "list_docs": list_docs,
        "search_docs": search_docs,
        "batch_search": batch_search,
        "import_docs": import_docs,
        "migrate_from_outline": migrate_from_outline,
        "sync_content_calendar": lambda **_: sync_content_calendar(),
        "link_docs": link_docs,
        "unlink_docs": unlink_docs,
        "read_backlinks": read_backlinks,
        "read_links": read_links,
        "retrieve_doc": retrieve_doc,
        "stitch_docs": stitch_docs,
        "verify_backfill": verify_backfill,
        "list_revisions": list_revisions,
        "get_revision": get_revision,
        "restore_revision": restore_revision
    }

    if action in actions:
        result = actions[action](**params)
        print(json.dumps(result, indent=2))
    else:
        print(json.dumps({"status": "error", "message": f"Unknown action: {action}"}))
