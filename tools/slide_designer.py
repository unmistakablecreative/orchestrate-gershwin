#!/usr/bin/env python3
"""
Slide Designer 3.0 - Presentation deck creation and management tool.

Actions:
- create_deck: Create a new presentation deck
- add_slide: Add a slide to a deck
- update_slide: Update an existing slide
- delete_slide: Delete a slide from a deck
- list_decks: List all presentation decks
- export_html: Export deck as self-contained HTML
- export_pdf: Export deck to PDF

Data Sources:
- data/slides.db: SQLite database for deck/slide content
- data/slide_designer_layouts.json: Layout definitions
- data/slide_themes.json: Theme definitions
- data/lucide_icons.json: Icon SVG paths
"""

import json
import sqlite3
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path

# Import response helper
from response_helper import get_success_message, get_error_message

# Paths
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "slides.db"
LAYOUTS_PATH = DATA_DIR / "slide_designer_layouts.json"
THEMES_PATH = DATA_DIR / "slide_themes.json"
ICONS_PATH = DATA_DIR / "lucide_icons.json"
OUTPUT_DIR = BASE_DIR / "semantic_memory" / "slides"

# Ensure output directory exists
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def get_db_connection():
    """Get SQLite connection with foreign keys enabled."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def load_layouts():
    """Load layout definitions from JSON."""
    with open(LAYOUTS_PATH, 'r') as f:
        return json.load(f)


def load_themes():
    """Load theme definitions from JSON."""
    with open(THEMES_PATH, 'r') as f:
        return json.load(f)


def load_icons():
    """Load icon definitions from JSON."""
    with open(ICONS_PATH, 'r') as f:
        return json.load(f)


def generate_id(prefix=""):
    """Generate a unique ID with optional prefix."""
    short_uuid = uuid.uuid4().hex[:8]
    if prefix:
        return f"{prefix}_{short_uuid}"
    return short_uuid


# ============================================================
# Action Functions
# ============================================================

def create_deck(params):
    """Create a new presentation deck."""
    title = params.get("title")
    if not title:
        return {"status": "error", "message": get_error_message("slide_designer", "create_deck", "title is required")}

    theme = params.get("theme", "dark_pro")

    # Validate theme exists
    themes_data = load_themes()
    if theme not in themes_data.get("themes", {}):
        available = list(themes_data.get("themes", {}).keys())
        return {"status": "error", "message": get_error_message("slide_designer", "create_deck", f"Invalid theme '{theme}'. Available: {available}")}

    deck_id = generate_id("deck")
    now = datetime.now().isoformat()

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO decks (id, title, theme, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
    """, (deck_id, title, theme, now, now))

    conn.commit()
    conn.close()

    return {
        "status": "success",
        "deck_id": deck_id,
        "title": title,
        "theme": theme,
        "message": get_success_message("slide_designer", "create_deck", {"title": title, "theme": theme})
    }

# Layout type aliases for common short names
LAYOUT_ALIASES = {
    "title": "title_hero",
    "hero": "title_hero",
    "content": "bullet_list",
    "bullets": "bullet_list",
    "stats": "stats_row",
    "numbers": "big_number",
    "quote": "quote",
    "closing": "cta_closing",
    "cta": "cta_closing",
    "divider": "section_divider",
    "image": "image_full",
    "text": "text_only",
    "icons": "icon_list",
    "steps": "numbered_steps",
    "chart": "chart_single",
    "agenda": "agenda",
    "team": "team_grid",
    "logos": "logo_grid",
    "comparison": "comparison_table",
    "timeline": "timeline_horizontal",
    "columns": "split_content",
    "two_column": "split_content",
    "three_column": "three_column",
    "grid": "four_grid"
}

def resolve_layout_type(layout_type):
    """Resolve layout type alias to full layout ID."""
    if layout_type in LAYOUT_ALIASES:
        return LAYOUT_ALIASES[layout_type]
    return layout_type



def add_slide(params):
    """Add a slide to a deck."""
    deck_id = params.get("deck_id")
    layout_type = resolve_layout_type(params.get("layout_type", ""))
    content = params.get("content")
    index = params.get("index")  # Optional, appends if omitted
    theme_override = params.get("theme_override")

    if not deck_id:
        return {"status": "error", "message": get_error_message("slide_designer", "add_slide", "deck_id is required")}
    if not layout_type:
        return {"status": "error", "message": get_error_message("slide_designer", "add_slide", "layout_type is required")}
    if not content:
        return {"status": "error", "message": get_error_message("slide_designer", "add_slide", "content is required")}

    # Validate layout exists
    layouts_data = load_layouts()
    layout_ids = [l["id"] for l in layouts_data.get("layouts", [])]
    if layout_type not in layout_ids:
        return {"status": "error", "message": get_error_message("slide_designer", "add_slide", f"Invalid layout_type '{layout_type}'. Available: {layout_ids}")}

    conn = get_db_connection()
    cursor = conn.cursor()

    # Check deck exists and get title
    cursor.execute("SELECT id, title FROM decks WHERE id = ?", (deck_id,))
    deck_row = cursor.fetchone()
    if not deck_row:
        conn.close()
        return {"status": "error", "message": get_error_message("slide_designer", "add_slide", f"Deck '{deck_id}' not found")}

    deck_title = deck_row["title"]

    # Get current max slide_index
    cursor.execute("SELECT MAX(slide_index) FROM slides WHERE deck_id = ?", (deck_id,))
    max_index = cursor.fetchone()[0]
    max_index = max_index if max_index is not None else -1

    # Determine slide index
    if index is not None:
        slide_index = index
        # Shift existing slides if inserting
        cursor.execute("""
            UPDATE slides SET slide_index = slide_index + 1
            WHERE deck_id = ? AND slide_index >= ?
        """, (deck_id, index))
    else:
        slide_index = max_index + 1

    slide_id = generate_id("slide")
    now = datetime.now().isoformat()
    content_json = json.dumps(content) if isinstance(content, dict) else content

    cursor.execute("""
        INSERT INTO slides (id, deck_id, slide_index, layout_type, content, theme_override, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (slide_id, deck_id, slide_index, layout_type, content_json, theme_override, now))

    # Update deck's updated_at
    cursor.execute("UPDATE decks SET updated_at = ? WHERE id = ?", (now, deck_id))

    conn.commit()
    conn.close()

    return {
        "status": "success",
        "slide_id": slide_id,
        "deck_id": deck_id,
        "slide_index": slide_index,
        "layout_type": layout_type,
        "message": get_success_message("slide_designer", "add_slide", {"deck_title": deck_title, "slide_index": slide_index})
    }


def update_slide(params):
    """Update an existing slide."""
    slide_id = params.get("slide_id")
    if not slide_id:
        return {"status": "error", "message": get_error_message("slide_designer", "update_slide", "slide_id is required")}

    conn = get_db_connection()
    cursor = conn.cursor()

    # Check slide exists
    cursor.execute("SELECT deck_id FROM slides WHERE id = ?", (slide_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return {"status": "error", "message": get_error_message("slide_designer", "update_slide", f"Slide '{slide_id}' not found")}

    deck_id = row["deck_id"]

    # Build update query
    updates = []
    values = []

    if "layout_type" in params:
        params["layout_type"] = resolve_layout_type(params["layout_type"])
        layouts_data = load_layouts()
        layout_ids = [l["id"] for l in layouts_data.get("layouts", [])]
        if params["layout_type"] not in layout_ids:
            conn.close()
            return {"status": "error", "message": get_error_message("slide_designer", "update_slide", f"Invalid layout_type '{params['layout_type']}'")}
        updates.append("layout_type = ?")
        values.append(params["layout_type"])

    if "content" in params:
        content_json = json.dumps(params["content"]) if isinstance(params["content"], dict) else params["content"]
        updates.append("content = ?")
        values.append(content_json)

    if "theme_override" in params:
        updates.append("theme_override = ?")
        values.append(params["theme_override"])

    if not updates:
        conn.close()
        return {"status": "error", "message": get_error_message("slide_designer", "update_slide", "No fields to update")}

    values.append(slide_id)
    query = f"UPDATE slides SET {', '.join(updates)} WHERE id = ?"
    cursor.execute(query, values)

    # Update deck's updated_at
    now = datetime.now().isoformat()
    cursor.execute("UPDATE decks SET updated_at = ? WHERE id = ?", (now, deck_id))

    conn.commit()
    conn.close()

    return {
        "status": "success",
        "slide_id": slide_id,
        "message": get_success_message("slide_designer", "update_slide", {"slide_id": slide_id})
    }


def delete_slide(params):
    """Delete a slide from a deck."""
    slide_id = params.get("slide_id")
    if not slide_id:
        return {"status": "error", "message": get_error_message("slide_designer", "delete_slide", "slide_id is required")}

    conn = get_db_connection()
    cursor = conn.cursor()

    # Get slide info before deletion
    cursor.execute("SELECT deck_id, slide_index FROM slides WHERE id = ?", (slide_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return {"status": "error", "message": get_error_message("slide_designer", "delete_slide", f"Slide '{slide_id}' not found")}

    deck_id = row["deck_id"]
    deleted_index = row["slide_index"]

    # Delete the slide
    cursor.execute("DELETE FROM slides WHERE id = ?", (slide_id,))

    # Reindex remaining slides
    cursor.execute("""
        UPDATE slides SET slide_index = slide_index - 1
        WHERE deck_id = ? AND slide_index > ?
    """, (deck_id, deleted_index))

    # Update deck's updated_at
    now = datetime.now().isoformat()
    cursor.execute("UPDATE decks SET updated_at = ? WHERE id = ?", (now, deck_id))

    conn.commit()
    conn.close()

    return {
        "status": "success",
        "slide_id": slide_id,
        "message": get_success_message("slide_designer", "delete_slide", {"slide_index": deleted_index})
    }


def list_decks(params):
    """List all presentation decks with slide counts."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT d.id, d.title, d.theme, d.created_at, d.updated_at,
               COUNT(s.id) as slide_count
        FROM decks d
        LEFT JOIN slides s ON d.id = s.deck_id
        GROUP BY d.id
        ORDER BY d.updated_at DESC
    """)

    decks = []
    for row in cursor.fetchall():
        decks.append({
            "id": row["id"],
            "title": row["title"],
            "theme": row["theme"],
            "slide_count": row["slide_count"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"]
        })

    conn.close()

    return {
        "status": "success",
        "decks": decks,
        "count": len(decks),
        "message": get_success_message("slide_designer", "list_decks", {"count": len(decks)})
    }


def get_deck(params):
    """Get a single deck with all its slides."""
    deck_id = params.get("deck_id")
    if not deck_id:
        return {"status": "error", "message": get_error_message("slide_designer", "get_deck", "deck_id is required")}

    conn = get_db_connection()
    cursor = conn.cursor()

    # Get deck info
    cursor.execute("SELECT * FROM decks WHERE id = ?", (deck_id,))
    deck_row = cursor.fetchone()
    if not deck_row:
        conn.close()
        return {"status": "error", "message": get_error_message("slide_designer", "get_deck", f"Deck '{deck_id}' not found")}

    # Get slides
    cursor.execute("""
        SELECT * FROM slides WHERE deck_id = ? ORDER BY slide_index
    """, (deck_id,))

    slides = []
    for row in cursor.fetchall():
        slides.append({
            "id": row["id"],
            "slide_index": row["slide_index"],
            "layout_type": row["layout_type"],
            "content": json.loads(row["content"]) if row["content"] else {},
            "theme_override": row["theme_override"],
            "created_at": row["created_at"]
        })

    conn.close()

    return {
        "status": "success",
        "deck": {
            "id": deck_row["id"],
            "title": deck_row["title"],
            "theme": deck_row["theme"],
            "created_at": deck_row["created_at"],
            "updated_at": deck_row["updated_at"],
            "slides": slides
        },
        "message": get_success_message("slide_designer", "get_deck", {"title": deck_row["title"], "slide_count": len(slides)})
    }


def delete_deck(params):
    """Delete a deck and all its slides."""
    deck_id = params.get("deck_id")
    if not deck_id:
        return {"status": "error", "message": get_error_message("slide_designer", "delete_deck", "deck_id is required")}

    conn = get_db_connection()
    cursor = conn.cursor()

    # Check deck exists
    cursor.execute("SELECT title FROM decks WHERE id = ?", (deck_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return {"status": "error", "message": get_error_message("slide_designer", "delete_deck", f"Deck '{deck_id}' not found")}

    title = row["title"]

    # Delete deck (CASCADE will delete slides)
    cursor.execute("DELETE FROM decks WHERE id = ?", (deck_id,))

    conn.commit()
    conn.close()

    return {
        "status": "success",
        "deck_id": deck_id,
        "message": get_success_message("slide_designer", "delete_deck", {"title": title})
    }


def render_slide_html(slide, theme, layouts_data, icons_data):
    """Render a single slide to HTML."""
    layout_type = slide["layout_type"]
    content = slide["content"]

    # Find layout definition
    layout = None
    for l in layouts_data.get("layouts", []):
        if l["id"] == layout_type:
            layout = l
            break

    if not layout:
        return f'<div class="slide error">Unknown layout: {layout_type}</div>'

    # Get theme colors
    theme_css = theme.get("css_vars", {})

    # Build CSS variables string
    css_vars = "; ".join([f"{k}: {v}" for k, v in theme_css.items()])

    # Render based on layout type
    html = f'<div class="slide layout-{layout_type}" style="{css_vars}">'

    # Title layouts
    if layout_type == "title_hero":
        headline = content.get("headline", "")
        subtitle = content.get("subtitle", "")
        html += f'''
            <div class="title-hero-content">
                <h1 class="hero-headline">{headline}</h1>
                {f'<p class="hero-subtitle">{subtitle}</p>' if subtitle else ''}
            </div>
        '''

    elif layout_type == "split_content":
        left_title = content.get("left_title", "")
        left_body = content.get("left_body", "")
        right_content = content.get("right_content", "")
        html += f'''
            <div class="split-left">
                <h2>{left_title}</h2>
                <p>{left_body}</p>
            </div>
            <div class="split-right">
                {right_content}
            </div>
        '''

    elif layout_type == "three_column":
        columns = content.get("columns", [])
        html += '<div class="three-column-grid">'
        for col in columns[:3]:
            icon_name = col.get("icon", "")
            icon_svg = icons_data.get("icons", {}).get(icon_name, "")
            html += f'''
                <div class="column-card">
                    <div class="column-icon">{icon_svg}</div>
                    <h3>{col.get("title", "")}</h3>
                    <p>{col.get("body", "")}</p>
                </div>
            '''
        html += '</div>'

    elif layout_type == "four_grid":
        items = content.get("items", [])
        html += '<div class="four-grid">'
        for item in items[:4]:
            icon_name = item.get("icon", "")
            icon_svg = icons_data.get("icons", {}).get(icon_name, "")
            html += f'''
                <div class="grid-card">
                    <div class="grid-icon">{icon_svg}</div>
                    <h3>{item.get("title", "")}</h3>
                    <p>{item.get("body", "")}</p>
                </div>
            '''
        html += '</div>'

    elif layout_type == "big_number":
        number = content.get("number", "")
        label = content.get("label", "")
        context = content.get("context", "")
        html += f'''
            <div class="big-number-content">
                <span class="big-number">{number}</span>
                <span class="big-label">{label}</span>
                {f'<p class="big-context">{context}</p>' if context else ''}
            </div>
        '''

    elif layout_type == "stats_row":
        stats = content.get("stats", [])
        html += '<div class="stats-row">'
        for stat in stats[:4]:
            html += f'''
                <div class="stat-card">
                    <span class="stat-number">{stat.get("number", "")}</span>
                    <span class="stat-label">{stat.get("label", "")}</span>
                </div>
            '''
        html += '</div>'

    elif layout_type == "quote":
        quote_text = content.get("quote_text", "")
        author_name = content.get("author_name", "")
        author_title = content.get("author_title", "")
        html += f'''
            <div class="quote-content">
                <blockquote>"{quote_text}"</blockquote>
                <div class="quote-attribution">
                    <span class="author-name">{author_name}</span>
                    {f'<span class="author-title">{author_title}</span>' if author_title else ''}
                </div>
            </div>
        '''

    elif layout_type == "bullet_list":
        title = content.get("title", "")
        bullets = content.get("bullets", [])
        html += f'<h2>{title}</h2><ul class="bullet-list">'
        for bullet in bullets:
            html += f'<li>{bullet}</li>'
        html += '</ul>'

    elif layout_type == "timeline_horizontal":
        points = content.get("points", [])
        html += '<div class="timeline-horizontal">'
        for i, point in enumerate(points):
            html += f'''
                <div class="timeline-point">
                    <div class="timeline-marker">{i + 1}</div>
                    <div class="timeline-label">{point.get("label", "")}</div>
                    <div class="timeline-body">{point.get("body", "")}</div>
                </div>
            '''
        html += '</div>'

    elif layout_type == "comparison_table":
        title = content.get("title", "")
        headers = content.get("headers", [])
        rows = content.get("rows", [])
        html += f'<h2>{title}</h2><table class="comparison-table"><thead><tr>'
        for header in headers:
            html += f'<th>{header}</th>'
        html += '</tr></thead><tbody>'
        for row in rows:
            html += '<tr>'
            for cell in row:
                html += f'<td>{cell}</td>'
            html += '</tr>'
        html += '</tbody></table>'

    elif layout_type == "team_grid":
        members = content.get("members", [])
        html += '<div class="team-grid">'
        for member in members:
            photo = member.get("photo", "")
            photo_html = f'<img src="{photo}" class="team-photo"/>' if photo else '<div class="team-photo-placeholder"></div>'
            html += f'''
                <div class="team-card">
                    {photo_html}
                    <h4>{member.get("name", "")}</h4>
                    <span class="team-title">{member.get("title", "")}</span>
                </div>
            '''
        html += '</div>'

    elif layout_type == "logo_grid":
        logos = content.get("logos", [])
        html += '<div class="logo-grid">'
        for logo in logos:
            if isinstance(logo, str):
                html += f'<div class="logo-cell"><img src="{logo}" class="partner-logo"/></div>'
            else:
                html += f'<div class="logo-cell"><img src="{logo.get("url", "")}" alt="{logo.get("name", "")}" class="partner-logo"/></div>'
        html += '</div>'

    elif layout_type == "cta_closing":
        headline = content.get("headline", "")
        subtext = content.get("subtext", "")
        cta_text = content.get("cta_text", "")
        cta_url = content.get("cta_url", "#")
        html += f'''
            <div class="cta-content">
                <h1>{headline}</h1>
                <p class="cta-subtext">{subtext}</p>
                {f'<a href="{cta_url}" class="cta-button">{cta_text}</a>' if cta_text else ''}
            </div>
        '''

    elif layout_type == "section_divider":
        title = content.get("title", "")
        subtitle = content.get("subtitle", "")
        html += f'''
            <div class="section-divider-content">
                <h1>{title}</h1>
                {f'<p>{subtitle}</p>' if subtitle else ''}
            </div>
        '''

    elif layout_type == "image_full":
        image_url = content.get("image_url", "")
        caption = content.get("caption", "")
        html += f'''
            <div class="image-full" style="background-image: url('{image_url}');">
                {f'<div class="image-caption">{caption}</div>' if caption else ''}
            </div>
        '''

    elif layout_type == "text_only":
        title = content.get("title", "")
        body = content.get("body", "")
        html += f'''
            <div class="text-only-content">
                <h2>{title}</h2>
                <p>{body}</p>
            </div>
        '''

    elif layout_type == "icon_list":
        title = content.get("title", "")
        items = content.get("items", [])
        html += f'<h2>{title}</h2><div class="icon-list">'
        for item in items:
            icon_name = item.get("icon", "")
            icon_svg = icons_data.get("icons", {}).get(icon_name, "")
            html += f'''
                <div class="icon-list-item">
                    <div class="icon-list-icon">{icon_svg}</div>
                    <span>{item.get("text", "")}</span>
                </div>
            '''
        html += '</div>'

    elif layout_type == "numbered_steps":
        title = content.get("title", "")
        steps = content.get("steps", [])
        html += f'<h2>{title}</h2><div class="numbered-steps">'
        for i, step in enumerate(steps):
            html += f'''
                <div class="step">
                    <div class="step-number">{i + 1}</div>
                    <div class="step-content">
                        <h4>{step.get("title", "")}</h4>
                        <p>{step.get("body", "")}</p>
                    </div>
                </div>
            '''
        html += '</div>'

    elif layout_type == "chart_single":
        title = content.get("title", "")
        chart_type = content.get("chart_type", "bar")
        chart_data = content.get("chart_data", {})
        insights = content.get("insights", "")
        # Note: Actual chart rendering would require Chart.js integration
        html += f'''
            <div class="chart-slide">
                <h2>{title}</h2>
                <div class="chart-container" data-chart-type="{chart_type}" data-chart='{json.dumps(chart_data)}'>
                    <canvas id="chart-{slide.get("id", "")}"></canvas>
                </div>
                {f'<p class="chart-insights">{insights}</p>' if insights else ''}
            </div>
        '''

    elif layout_type == "agenda":
        title = content.get("title", "Agenda")
        items = content.get("items", [])
        html += f'<h2>{title}</h2><div class="agenda-list">'
        for i, item in enumerate(items):
            html += f'''
                <div class="agenda-item">
                    <span class="agenda-number">{i + 1:02d}</span>
                    <span class="agenda-text">{item}</span>
                </div>
            '''
        html += '</div>'

    else:
        # Generic fallback
        html += f'<div class="generic-content"><pre>{json.dumps(content, indent=2)}</pre></div>'

    html += '</div>'
    return html


def get_slide_css():
    """Return CSS for slide rendering."""
    return """
/* Slide Designer 3.0 - Slide Styles */
.slide {
    width: 1920px;
    height: 1080px;
    position: relative;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 80px;
    box-sizing: border-box;
    background: var(--theme-bg);
    color: var(--theme-text);
    font-family: var(--theme-font-body);
    overflow: hidden;
}

.slide h1, .slide h2, .slide h3, .slide h4 {
    font-family: var(--theme-font-heading);
    color: var(--theme-text);
    margin: 0 0 24px 0;
}

.slide h1 { font-size: 72px; font-weight: 700; }
.slide h2 { font-size: 48px; font-weight: 600; }
.slide h3 { font-size: 32px; font-weight: 600; }
.slide h4 { font-size: 24px; font-weight: 600; }

.slide p { font-size: 24px; line-height: 1.6; color: var(--theme-text-secondary); }

/* Title Hero */
.layout-title_hero .title-hero-content { text-align: center; }
.layout-title_hero .hero-headline { font-size: 96px; margin-bottom: 32px; }
.layout-title_hero .hero-subtitle { font-size: 36px; color: var(--theme-text-secondary); }

/* Split Content */
.layout-split_content { display: grid; grid-template-columns: 1fr 1fr; gap: 80px; }
.split-left, .split-right { display: flex; flex-direction: column; justify-content: center; }

/* Three Column */
.three-column-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 48px; width: 100%; }
.column-card { text-align: center; padding: 40px; background: var(--theme-surface); border-radius: 16px; }
.column-icon { width: 64px; height: 64px; margin: 0 auto 24px; }
.column-icon svg { width: 100%; height: 100%; stroke: var(--theme-accent); }

/* Four Grid */
.four-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 40px; width: 100%; }
.grid-card { padding: 40px; background: var(--theme-surface); border-radius: 16px; }
.grid-icon { width: 48px; height: 48px; margin-bottom: 16px; }
.grid-icon svg { width: 100%; height: 100%; stroke: var(--theme-accent); }

/* Big Number */
.big-number-content { text-align: center; }
.big-number { font-size: 200px; font-weight: 800; color: var(--theme-accent); display: block; line-height: 1; }
.big-label { font-size: 48px; color: var(--theme-text); display: block; margin-top: 24px; }
.big-context { font-size: 24px; margin-top: 16px; }

/* Stats Row */
.stats-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 40px; width: 100%; }
.stat-card { text-align: center; padding: 40px; background: var(--theme-surface); border-radius: 16px; }
.stat-number { font-size: 64px; font-weight: 700; color: var(--theme-accent); display: block; }
.stat-label { font-size: 20px; color: var(--theme-text-secondary); margin-top: 8px; display: block; }

/* Quote */
.quote-content { text-align: center; max-width: 1200px; }
.quote-content blockquote { font-size: 48px; font-style: italic; line-height: 1.4; margin: 0 0 48px 0; color: var(--theme-text); }
.quote-attribution { display: flex; flex-direction: column; gap: 8px; }
.author-name { font-size: 28px; font-weight: 600; }
.author-title { font-size: 20px; color: var(--theme-text-secondary); }

/* Bullet List */
.bullet-list { list-style: none; padding: 0; margin: 32px 0 0 0; }
.bullet-list li { font-size: 28px; padding: 16px 0; padding-left: 40px; position: relative; }
.bullet-list li::before { content: ''; position: absolute; left: 0; top: 50%; transform: translateY(-50%); width: 12px; height: 12px; background: var(--theme-accent); border-radius: 50%; }

/* Timeline */
.timeline-horizontal { display: flex; justify-content: space-between; width: 100%; position: relative; }
.timeline-horizontal::before { content: ''; position: absolute; top: 24px; left: 48px; right: 48px; height: 4px; background: var(--theme-border); }
.timeline-point { text-align: center; flex: 1; position: relative; }
.timeline-marker { width: 48px; height: 48px; background: var(--theme-accent); border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: 20px; margin: 0 auto 24px; position: relative; z-index: 1; }
.timeline-label { font-size: 24px; font-weight: 600; margin-bottom: 8px; }
.timeline-body { font-size: 18px; color: var(--theme-text-secondary); padding: 0 16px; }

/* Comparison Table */
.comparison-table { width: 100%; border-collapse: collapse; margin-top: 32px; }
.comparison-table th, .comparison-table td { padding: 20px 32px; text-align: left; border-bottom: 1px solid var(--theme-border); }
.comparison-table th { background: var(--theme-surface); font-weight: 600; font-size: 20px; }
.comparison-table td { font-size: 18px; }

/* Team Grid */
.team-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 32px; width: 100%; }
.team-card { text-align: center; }
.team-photo { width: 160px; height: 160px; border-radius: 50%; object-fit: cover; margin-bottom: 16px; }
.team-photo-placeholder { width: 160px; height: 160px; border-radius: 50%; background: var(--theme-surface); margin: 0 auto 16px; }
.team-card h4 { margin-bottom: 4px; }
.team-title { font-size: 16px; color: var(--theme-text-secondary); }

/* Logo Grid */
.logo-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 48px; width: 100%; }
.logo-cell { display: flex; align-items: center; justify-content: center; padding: 32px; background: var(--theme-surface); border-radius: 16px; }
.partner-logo { max-width: 200px; max-height: 80px; object-fit: contain; }

/* CTA Closing */
.cta-content { text-align: center; }
.cta-content h1 { font-size: 72px; margin-bottom: 24px; }
.cta-subtext { font-size: 28px; margin-bottom: 48px; }
.cta-button { display: inline-block; padding: 24px 64px; background: var(--theme-accent); color: white; font-size: 24px; font-weight: 600; text-decoration: none; border-radius: 12px; }

/* Section Divider */
.section-divider-content { text-align: center; }
.section-divider-content h1 { font-size: 80px; }

/* Image Full */
.image-full { width: 100%; height: 100%; background-size: cover; background-position: center; position: absolute; top: 0; left: 0; }
.image-caption { position: absolute; bottom: 40px; left: 40px; right: 40px; padding: 24px; background: rgba(0,0,0,0.7); color: white; font-size: 24px; border-radius: 8px; }

/* Text Only */
.text-only-content { max-width: 1400px; }
.text-only-content h2 { margin-bottom: 32px; }
.text-only-content p { font-size: 28px; line-height: 1.8; }

/* Icon List */
.icon-list { margin-top: 32px; }
.icon-list-item { display: flex; align-items: center; gap: 24px; padding: 16px 0; font-size: 24px; }
.icon-list-icon { width: 40px; height: 40px; }
.icon-list-icon svg { width: 100%; height: 100%; stroke: var(--theme-accent); }

/* Numbered Steps */
.numbered-steps { margin-top: 32px; }
.step { display: flex; gap: 32px; padding: 24px 0; }
.step-number { width: 56px; height: 56px; background: var(--theme-accent); color: white; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 24px; font-weight: 700; flex-shrink: 0; }
.step-content h4 { margin-bottom: 8px; }
.step-content p { font-size: 20px; margin: 0; }

/* Chart */
.chart-slide { width: 100%; }
.chart-slide h2 { text-align: center; margin-bottom: 40px; }
.chart-container { width: 100%; height: 600px; display: flex; align-items: center; justify-content: center; }
.chart-insights { text-align: center; margin-top: 24px; }

/* Agenda */
.agenda-list { margin-top: 40px; }
.agenda-item { display: flex; align-items: center; gap: 32px; padding: 24px 0; border-bottom: 1px solid var(--theme-border); }
.agenda-number { font-size: 24px; font-weight: 700; color: var(--theme-accent); }
.agenda-text { font-size: 28px; }

/* Preview Scale */
.slide-preview {
    transform-origin: top left;
    box-shadow: var(--theme-shadow);
    border-radius: 8px;
    overflow: hidden;
}
"""


def export_html(params):
    """Export deck as self-contained HTML."""
    deck_id = params.get("deck_id")
    if not deck_id:
        return {"status": "error", "message": get_error_message("slide_designer", "export_html", "deck_id is required")}

    output_path = params.get("output_path")

    # Get deck data
    deck_result = get_deck({"deck_id": deck_id})
    if deck_result["status"] != "success":
        return deck_result

    deck = deck_result["deck"]
    slides = deck["slides"]

    # Load resources
    themes_data = load_themes()
    layouts_data = load_layouts()
    icons_data = load_icons()

    # Get theme
    theme_name = deck["theme"]
    theme = themes_data.get("themes", {}).get(theme_name, themes_data.get("themes", {}).get("dark_pro", {}))

    # Render slides
    slides_html = ""
    for slide in slides:
        slides_html += render_slide_html(slide, theme, layouts_data, icons_data)

    # Build full HTML
    css = get_slide_css()
    theme_css_vars = "; ".join([f"{k}: {v}" for k, v in theme.get("css_vars", {}).items()])

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{deck["title"]}</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Poppins:wght@600;700;800&family=Playfair+Display:wght@700&family=Merriweather:wght@700&family=JetBrains+Mono:wght@400;600;700&display=swap" rel="stylesheet">
    <style>
        :root {{ {theme_css_vars} }}
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ background: #0a0a0a; min-height: 100vh; padding: 40px; }}
        .deck-container {{ max-width: 1200px; margin: 0 auto; }}
        .deck-title {{ color: white; font-family: Inter, sans-serif; font-size: 32px; margin-bottom: 32px; }}
        .slide-wrapper {{ margin-bottom: 40px; }}
        .slide-number {{ color: #666; font-family: Inter, sans-serif; font-size: 14px; margin-bottom: 8px; }}
        {css}
        .slide {{ transform: scale(0.5); transform-origin: top left; margin-bottom: -540px; }}
    </style>
</head>
<body>
    <div class="deck-container">
        <h1 class="deck-title">{deck["title"]}</h1>
"""

    for i, slide in enumerate(slides):
        html += f"""
        <div class="slide-wrapper">
            <div class="slide-number">Slide {i + 1}</div>
            {render_slide_html(slide, theme, layouts_data, icons_data)}
        </div>
"""

    html += """
    </div>
</body>
</html>
"""

    # Determine output path
    if not output_path:
        safe_title = "".join(c if c.isalnum() or c in "- _" else "_" for c in deck["title"])
        output_path = str(OUTPUT_DIR / f"{safe_title}.html")

    # Write file
    with open(output_path, 'w') as f:
        f.write(html)

    return {
        "status": "success",
        "output_path": output_path,
        "slide_count": len(slides),
        "message": get_success_message("slide_designer", "export_html", {"slide_count": len(slides), "output_path": output_path})
    }


def export_pdf(params):
    """Export deck to PDF via Puppeteer/Chrome."""
    deck_id = params.get("deck_id")
    if not deck_id:
        return {"status": "error", "message": get_error_message("slide_designer", "export_pdf", "deck_id is required")}

    output_path = params.get("output_path")

    # First export to HTML
    deck_result = get_deck({"deck_id": deck_id})
    if deck_result["status"] != "success":
        return deck_result

    deck = deck_result["deck"]

    # Determine paths
    safe_title = "".join(c if c.isalnum() or c in "- _" else "_" for c in deck["title"])
    html_path = str(OUTPUT_DIR / f"{safe_title}_temp.html")

    if not output_path:
        output_path = str(OUTPUT_DIR / f"{safe_title}.pdf")

    # Export HTML first
    html_result = export_html({"deck_id": deck_id, "output_path": html_path})
    if html_result["status"] != "success":
        return html_result

    # Use Chrome/Chromium to generate PDF
    import subprocess

    # Try different Chrome paths
    chrome_paths = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "google-chrome",
        "chromium"
    ]

    chrome_path = None
    for path in chrome_paths:
        if os.path.exists(path) or subprocess.run(["which", path], capture_output=True).returncode == 0:
            chrome_path = path
            break

    if not chrome_path:
        # Clean up temp HTML
        os.remove(html_path)
        return {
            "status": "error",
            "message": get_error_message("slide_designer", "export_pdf", "Chrome/Chromium not found"),
            "html_fallback": html_path.replace("_temp.html", ".html")
        }

    try:
        result = subprocess.run([
            chrome_path,
            "--headless",
            "--disable-gpu",
            f"--print-to-pdf={output_path}",
            "--no-margins",
            f"file://{html_path}"
        ], capture_output=True, timeout=30)

        # Clean up temp HTML
        os.remove(html_path)

        if result.returncode != 0:
            return {"status": "error", "message": get_error_message("slide_designer", "export_pdf", result.stderr.decode())}

        return {
            "status": "success",
            "output_path": output_path,
            "slide_count": len(deck["slides"]),
            "message": get_success_message("slide_designer", "export_pdf", {"slide_count": len(deck["slides"]), "output_path": output_path})
        }

    except subprocess.TimeoutExpired:
        os.remove(html_path)
        return {"status": "error", "message": get_error_message("slide_designer", "export_pdf", "PDF generation timed out")}
    except Exception as e:
        if os.path.exists(html_path):
            os.remove(html_path)
        return {"status": "error", "message": get_error_message("slide_designer", "export_pdf", str(e))}


def update_deck(params):
    """Update deck title or theme."""
    deck_id = params.get("deck_id")
    if not deck_id:
        return {"status": "error", "message": get_error_message("slide_designer", "update_deck", "deck_id is required")}

    conn = get_db_connection()
    cursor = conn.cursor()

    # Check deck exists
    cursor.execute("SELECT id FROM decks WHERE id = ?", (deck_id,))
    if not cursor.fetchone():
        conn.close()
        return {"status": "error", "message": get_error_message("slide_designer", "update_deck", f"Deck '{deck_id}' not found")}

    updates = []
    values = []

    if "title" in params:
        updates.append("title = ?")
        values.append(params["title"])

    if "theme" in params:
        themes_data = load_themes()
        if params["theme"] not in themes_data.get("themes", {}):
            conn.close()
            return {"status": "error", "message": get_error_message("slide_designer", "update_deck", f"Invalid theme '{params['theme']}'")}
        updates.append("theme = ?")
        values.append(params["theme"])

    if not updates:
        conn.close()
        return {"status": "error", "message": get_error_message("slide_designer", "update_deck", "No fields to update")}

    updates.append("updated_at = ?")
    values.append(datetime.now().isoformat())
    values.append(deck_id)

    query = f"UPDATE decks SET {', '.join(updates)} WHERE id = ?"
    cursor.execute(query, values)

    conn.commit()
    conn.close()

    return {
        "status": "success",
        "deck_id": deck_id,
        "message": get_success_message("slide_designer", "update_deck", {"deck_id": deck_id})
    }


def reorder_slides(params):
    """Reorder slides within a deck."""
    deck_id = params.get("deck_id")
    slide_order = params.get("slide_order")  # List of slide_ids in new order

    if not deck_id:
        return {"status": "error", "message": get_error_message("slide_designer", "reorder_slides", "deck_id is required")}
    if not slide_order or not isinstance(slide_order, list):
        return {"status": "error", "message": get_error_message("slide_designer", "reorder_slides", "slide_order must be a list of slide IDs")}

    conn = get_db_connection()
    cursor = conn.cursor()

    # Verify all slides belong to this deck
    cursor.execute("SELECT id FROM slides WHERE deck_id = ?", (deck_id,))
    existing_ids = {row["id"] for row in cursor.fetchall()}

    if set(slide_order) != existing_ids:
        conn.close()
        return {"status": "error", "message": get_error_message("slide_designer", "reorder_slides", "slide_order must contain all and only slides from this deck")}

    # Update indexes
    for new_index, slide_id in enumerate(slide_order):
        cursor.execute("UPDATE slides SET slide_index = ? WHERE id = ?", (new_index, slide_id))

    # Update deck's updated_at
    now = datetime.now().isoformat()
    cursor.execute("UPDATE decks SET updated_at = ? WHERE id = ?", (now, deck_id))

    conn.commit()
    conn.close()

    return {
        "status": "success",
        "deck_id": deck_id,
        "message": get_success_message("slide_designer", "reorder_slides", {"count": len(slide_order)})
    }


def list_layouts(params):
    """List available layout types."""
    layouts_data = load_layouts()
    layouts = []

    for layout in layouts_data.get("layouts", []):
        layouts.append({
            "id": layout["id"],
            "name": layout["name"],
            "category": layout.get("category", ""),
            "description": layout.get("description", ""),
            "use_case": layout.get("use_case", "")
        })

    return {
        "status": "success",
        "layouts": layouts,
        "count": len(layouts),
        "message": get_success_message("slide_designer", "list_layouts", {"count": len(layouts)})
    }


def list_themes(params):
    """List available themes."""
    themes_data = load_themes()
    themes = []

    for theme_id, theme in themes_data.get("themes", {}).items():
        themes.append({
            "id": theme_id,
            "name": theme["name"],
            "description": theme.get("description", ""),
            "default": theme.get("default", False),
            "colors": theme.get("colors", {})
        })

    return {
        "status": "success",
        "themes": themes,
        "count": len(themes),
        "message": get_success_message("slide_designer", "list_themes", {"count": len(themes)})
    }


# ============================================================
# Main Entry Point
# ============================================================

def execute(action, params):
    """Main entry point for execution_hub."""
    if action == "create_deck":
        result = create_deck(params)
    elif action == "add_slide":
        result = add_slide(params)
    elif action == "update_slide":
        result = update_slide(params)
    elif action == "delete_slide":
        result = delete_slide(params)
    elif action == "list_decks":
        result = list_decks(params)
    elif action == "get_deck":
        result = get_deck(params)
    elif action == "delete_deck":
        result = delete_deck(params)
    elif action == "export_html":
        result = export_html(params)
    elif action == "export_pdf":
        result = export_pdf(params)
    elif action == "update_deck":
        result = update_deck(params)
    elif action == "reorder_slides":
        result = reorder_slides(params)
    elif action == "list_layouts":
        result = list_layouts(params)
    elif action == "list_themes":
        result = list_themes(params)
    else:
        result = {"status": "error", "message": get_error_message("slide_designer", action, f"Unknown action: {action}")}

    return result


if __name__ == "__main__":
    # CLI mode - supports execution_hub pattern: script.py action --params '{...}'
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("action", help="Action to perform")
    parser.add_argument("--params", default="{}", help="JSON params")
    args = parser.parse_args()

    params = json.loads(args.params) if args.params else {}
    result = execute(args.action, params)
    print(json.dumps(result, indent=2))
