#!/usr/bin/env python3
"""
writing_linter.py - Auto-fix common AI writing pattern errors

Clean rebuild v5 - Paragraph-aware architecture from the ground up.

Actions:
- lint_and_fix: Takes raw text, returns cleaned text (silent, no scoring)
- lint: Legacy wrapper that returns (text, score, violations) for backward compat
"""

import re
from typing import List, Tuple, Dict, Optional

from response_helper import get_success_message, get_error_message
# Full docstrings and function descriptions: data/orchestrate_docstrings.json

HEDGING_PHRASES = [
    "i want to be honest",
    "to be honest",
    "the truth is",
    "here is the thing",
    "here's the thing",
    "it is worth noting",
    "it's worth noting",
    "needless to say",
    "at the end of the day",
    "in many ways",
    "to some extent",
    "quite frankly",
    "let me be clear",
    "to be clear",
    "if i'm being honest",
    "honestly",
    "truthfully",
    "in all honesty",
]

ATTRIBUTION_PHRASES = [
    "research shows",
    "studies suggest",
    "experts say",
    "scientists have found",
    "data shows",
    "evidence suggests",
    "a professor at",
    "one of the most replicated findings",
    "according to research",
    "research suggests",
    "studies have shown",
    "experts agree",
    "science tells us",
]

CONNECTORS = ["Also,", "And", "Additionally,"]
_connector_index = 0

PROPER_NOUNS = {
    "claude", "ai", "mark", "laura", "tzvi", "angela", "gpt", "openai",
    "anthropic", "google", "microsoft", "amazon", "apple", "meta", "facebook",
    "twitter", "linkedin", "instagram", "youtube", "reddit", "github",
    "srini", "srinivas", "orchestrate", "jarvis",
}

def _get_next_connector() -> str:
    global _connector_index
    connector = CONNECTORS[_connector_index % len(CONNECTORS)]
    _connector_index += 1
    return connector

def _reset_connector_index():
    global _connector_index
    _connector_index = 0

def _split_into_sentences(text: str) -> List[str]:
    if not text or not text.strip():
        return []

    pattern = r'(?<![A-Z])(?<!\b(?:Mr|Mrs|Ms|Dr|Prof|Jr|Sr|vs|etc|e\.g|i\.e))\. +(?=[A-Z"])|(?<=[.!?])\s*$|(?<=[!?]) +(?=[A-Z"])'

    sentences = []
    current = []
    words = text.split()

    for i, word in enumerate(words):
        current.append(word)
        if word.endswith('.') or word.endswith('!') or word.endswith('?'):
            if i + 1 < len(words):
                next_word = words[i + 1]
                if word.rstrip('.!?').lower() in ['mr', 'mrs', 'ms', 'dr', 'prof', 'jr', 'sr', 'vs', 'etc', 'e.g', 'i.e']:
                    continue
                if next_word[0].isupper() or next_word[0] == '"':
                    sentences.append(' '.join(current))
                    current = []
            else:
                sentences.append(' '.join(current))
                current = []

    if current:
        sentences.append(' '.join(current))

    return [s.strip() for s in sentences if s.strip()]

def _has_protected_formatting(sentence: str) -> bool:
    if '—' in sentence:
        return True
    if sentence.rstrip().endswith(':'):
        return True
    if re.search(r'\*[^*]+\*', sentence):
        return True
    if re.search(r'_[^_]+_', sentence):
        return True
    if re.search(r'\*\*[^*]+\*\*', sentence):
        return True
    if re.search(r'__[^_]+__', sentence):
        return True
    return False

def _is_proper_noun(word: str) -> bool:
    return word.lower() in PROPER_NOUNS

def _adjust_case_after_connector(word: str) -> str:
    if _is_proper_noun(word):
        return word
    lowercase_starters = {'she', 'he', 'it', 'they', 'this', 'that', 'there', 'these', 'those', 'we', 'i'}
    if word.lower() in lowercase_starters:
        return word.lower()
    if word and word[0].isupper() and not _is_proper_noun(word):
        return word[0].lower() + word[1:] if len(word) > 1 else word.lower()
    return word

def fix_empty_hedging(paragraph: str) -> str:
    sentences = _split_into_sentences(paragraph)
    if not sentences:
        return paragraph

    cleaned = []
    for sentence in sentences:
        if _has_protected_formatting(sentence):
            cleaned.append(sentence)
            continue

        sentence_lower = sentence.lower()
        has_hedging = False
        for phrase in HEDGING_PHRASES:
            if phrase in sentence_lower:
                has_hedging = True
                break

        if not has_hedging:
            cleaned.append(sentence)

    return ' '.join(cleaned)

def fix_floating_attribution(paragraph: str) -> str:
    sentences = _split_into_sentences(paragraph)
    if not sentences:
        return paragraph

    cleaned = []
    for sentence in sentences:
        if _has_protected_formatting(sentence):
            cleaned.append(sentence)
            continue

        sentence_lower = sentence.lower()
        has_attribution = False
        for phrase in ATTRIBUTION_PHRASES:
            if phrase in sentence_lower:
                has_attribution = True
                break

        if not has_attribution:
            cleaned.append(sentence)

    return ' '.join(cleaned)

def _is_fragment(sentence: str) -> bool:
    words = sentence.rstrip('.!?').split()
    if len(words) > 3:
        return False
    if len(words) == 0:
        return False

    common_verbs = {'is', 'are', 'was', 'were', 'be', 'been', 'being',
                    'have', 'has', 'had', 'do', 'does', 'did',
                    'can', 'could', 'will', 'would', 'shall', 'should',
                    'may', 'might', 'must', 'get', 'gets', 'got',
                    'go', 'goes', 'went', 'come', 'comes', 'came',
                    'make', 'makes', 'made', 'take', 'takes', 'took',
                    'know', 'knows', 'knew', 'think', 'thinks', 'thought',
                    'see', 'sees', 'saw', 'want', 'wants', 'wanted',
                    'need', 'needs', 'needed', 'feel', 'feels', 'felt',
                    'matter', 'matters', 'mattered', 'exist', 'exists',
                    'work', 'works', 'worked', 'help', 'helps', 'helped',
                    'start', 'starts', 'started', 'end', 'ends', 'ended',
                    'change', 'changes', 'changed', 'stay', 'stays', 'stayed',
                    'live', 'lives', 'lived', 'die', 'dies', 'died',
                    'win', 'wins', 'won', 'lose', 'loses', 'lost',
                    'fail', 'fails', 'failed', 'succeed', 'succeeds', 'succeeded'}

    words_lower = [w.lower() for w in words]
    has_verb = any(w in common_verbs for w in words_lower)

    return not has_verb

def fix_consecutive_fragments(paragraph: str) -> str:
    sentences = _split_into_sentences(paragraph)
    if not sentences:
        return paragraph

    is_frag = [_is_fragment(s) and not _has_protected_formatting(s) for s in sentences]

    to_delete = set()
    i = 0
    while i < len(sentences):
        if is_frag[i]:
            run_start = i
            while i < len(sentences) and is_frag[i]:
                i += 1
            run_end = i
            if run_end - run_start >= 2:
                for j in range(run_start, run_end):
                    to_delete.add(j)
        else:
            i += 1

    cleaned = [s for idx, s in enumerate(sentences) if idx not in to_delete]
    return ' '.join(cleaned)

def fix_sentence_tricolon(paragraph: str) -> str:
    sentences = _split_into_sentences(paragraph)
    if len(sentences) < 3:
        return paragraph

    result = []
    i = 0
    while i < len(sentences):
        if i + 2 < len(sentences):
            s1, s2, s3 = sentences[i], sentences[i+1], sentences[i+2]

            if (_has_protected_formatting(s1) or
                _has_protected_formatting(s2) or
                _has_protected_formatting(s3)):
                result.append(sentences[i])
                i += 1
                continue

            words1 = s1.split()
            words2 = s2.split()
            words3 = s3.split()

            if words1 and words2 and words3:
                first1 = words1[0].lower().rstrip('.,!?')
                first2 = words2[0].lower().rstrip('.,!?')
                first3 = words3[0].lower().rstrip('.,!?')

                if first1 == first2 == first3:
                    result.append(s1)

                    adjusted_word2 = _adjust_case_after_connector(words2[0])
                    new_s2 = "Also, " + adjusted_word2 + (' ' + ' '.join(words2[1:]) if len(words2) > 1 else '')
                    result.append(new_s2)

                    adjusted_word3 = _adjust_case_after_connector(words3[0])
                    new_s3 = "And " + adjusted_word3 + (' ' + ' '.join(words3[1:]) if len(words3) > 1 else '')
                    result.append(new_s3)

                    i += 3
                    continue

        result.append(sentences[i])
        i += 1

    return ' '.join(result)

def fix_repetitive_parallel(paragraph: str) -> str:
    sentences = _split_into_sentences(paragraph)
    if len(sentences) < 2:
        return paragraph

    result = [sentences[0]]

    for i in range(1, len(sentences)):
        prev = sentences[i - 1]
        curr = sentences[i]

        if _has_protected_formatting(prev) or _has_protected_formatting(curr):
            result.append(curr)
            continue

        curr_first = curr.split()[0] if curr.split() else ""
        if curr_first.rstrip(',') in ['Also', 'And', 'Additionally']:
            result.append(curr)
            continue

        prev_words = prev.split()
        curr_words = curr.split()

        if len(prev_words) >= 2 and len(curr_words) >= 2:
            if prev_words[0].lower().rstrip('.,!?') == curr_words[0].lower().rstrip('.,!?'):
                min_len = min(len(prev_words), len(curr_words))
                has_parallel = False
                for j in range(1, min(min_len, 5)):
                    if prev_words[j].lower().rstrip('.,!?') == curr_words[j].lower().rstrip('.,!?'):
                        has_parallel = True
                        break

                if has_parallel:
                    connector = _get_next_connector()
                    adjusted_first = _adjust_case_after_connector(curr_words[0])
                    new_sentence = connector + " " + adjusted_first
                    if len(curr_words) > 1:
                        new_sentence += " " + ' '.join(curr_words[1:])
                    result.append(new_sentence)
                    continue

        result.append(curr)

    return ' '.join(result)

def _split_on_blank_lines(text: str) -> List[str]:
    text = text.replace('\r\n', '\n').replace('\r', '\n')

    if '<p>' in text or '<h' in text or '<hr' in text:
        return _split_html_blocks(text)

    paragraphs = re.split(r'\n\s*\n', text)

    return [p for p in paragraphs if p.strip()]

def _split_html_blocks(text: str) -> List[str]:
    blocks = []

    block_pattern = r'(<(?:p|h[1-6]|hr|ul|ol|li|blockquote|div)[^>]*>.*?</(?:p|h[1-6]|ul|ol|li|blockquote|div)>|<(?:p|h[1-6]|hr|ul|ol|li|blockquote|div)[^>]*/?>|<hr[^>]*>)'

    matches = list(re.finditer(block_pattern, text, re.IGNORECASE | re.DOTALL))

    if not matches:
        return [text] if text.strip() else []

    for match in matches:
        block = match.group(0).strip()
        if block:
            blocks.append(block)

    return blocks

def _is_protected_block(paragraph: str) -> bool:
    stripped = paragraph.strip()
    if not stripped:
        return True

    first_line = stripped.split('\n')[0].strip()

    if first_line.startswith('#'):
        return True

    if re.match(r'^<h[1-6][\s>]', first_line, re.IGNORECASE):
        return True

    if first_line.startswith('---') or first_line.startswith('***') or first_line.startswith('___'):
        return True

    if first_line.lower().startswith('<hr'):
        return True

    if re.match(r'^[-*]\s', first_line):
        return True
    if re.match(r'^\d+\.\s', first_line):
        return True

    if re.match(r'^<(ul|ol|li)[\s>]', first_line, re.IGNORECASE):
        return True

    return False

def _rejoin_with_blank_lines(paragraphs: List[str]) -> str:
    return '\n\n'.join(p for p in paragraphs if p.strip())

def _unwrap_html_paragraph(para: str) -> Tuple[str, str, str]:
    match = re.match(r'^(<p[^>]*>)(.*)(</p>)$', para, re.IGNORECASE | re.DOTALL)
    if match:
        return match.group(1), match.group(2), match.group(3)
    return '', para, ''

def _wrap_html_paragraph(prefix: str, content: str, suffix: str) -> str:
    if prefix and suffix:
        return f'{prefix}{content}{suffix}'
    return content

def lint_and_fix(text: str) -> str:
    if not text or not text.strip():
        return text

    _reset_connector_index()

    paragraphs = _split_on_blank_lines(text)
    cleaned_paragraphs = []

    for para in paragraphs:
        if _is_protected_block(para):
            cleaned_paragraphs.append(para)
            continue

        prefix, content, suffix = _unwrap_html_paragraph(para)

        content = fix_empty_hedging(content)
        content = fix_floating_attribution(content)
        content = fix_consecutive_fragments(content)
        content = fix_sentence_tricolon(content)
        content = fix_repetitive_parallel(content)

        para = _wrap_html_paragraph(prefix, content, suffix)

        if content.strip():
            cleaned_paragraphs.append(para)

    return _rejoin_with_blank_lines(cleaned_paragraphs)

def lint(text: str) -> Dict:
    """Returns dict with fixed_text and change_log for doc_editor compatibility."""
    fixed = lint_and_fix(text)
    return {"fixed_text": fixed, "change_log": []}


def action_lint(params: Dict) -> Dict:
    """Lint a document and return issues found.

    Args:
        params: {"text": str} or {"doc_id": str}

    Returns:
        {"status": "success", "fixed_text": str, "issue_count": int, "message": str}
    """
    text = params.get("text", "")
    if not text:
        return {"status": "error", "message": get_error_message("writing_linter", "lint", "text is required")}

    original_len = len(text)
    fixed = lint_and_fix(text)
    fixed_len = len(fixed)

    # Estimate issue count based on text reduction
    issue_count = max(0, (original_len - fixed_len) // 50) if original_len > fixed_len else 0

    return {
        "status": "success",
        "fixed_text": fixed,
        "issue_count": issue_count,
        "message": get_success_message("writing_linter", "lint", {"issue_count": issue_count})
    }


def action_fix(params: Dict) -> Dict:
    """Fix issues in a document.

    Args:
        params: {"text": str}

    Returns:
        {"status": "success", "fixed_text": str, "fix_count": int, "message": str}
    """
    text = params.get("text", "")
    if not text:
        return {"status": "error", "message": get_error_message("writing_linter", "fix", "text is required")}

    original_len = len(text)
    fixed = lint_and_fix(text)
    fixed_len = len(fixed)

    # Estimate fix count based on text changes
    fix_count = max(0, (original_len - fixed_len) // 50) if original_len > fixed_len else 0

    return {
        "status": "success",
        "fixed_text": fixed,
        "fix_count": fix_count,
        "message": get_success_message("writing_linter", "fix", {"fix_count": fix_count})
    }

if __name__ == "__main__":
    import argparse
    import json
    import sys

    parser = argparse.ArgumentParser(description="Writing linter - auto-fix AI writing patterns")
    parser.add_argument("action", nargs="?", help="Action to perform (lint, fix)")
    parser.add_argument("--params", type=str, default="{}", help="JSON params for action")
    parser.add_argument("--file", "-f", help="File to lint (in-place edit)")
    parser.add_argument("--text", "-t", help="Text to lint (prints result)")

    args = parser.parse_args()

    # Action-based invocation (execution_hub compatible)
    if args.action and args.action in ("lint", "fix"):
        try:
            params = json.loads(args.params)
        except json.JSONDecodeError as e:
            print(json.dumps({"status": "error", "message": f"Invalid JSON params: {e}"}))
            sys.exit(1)

        if args.action == "lint":
            result = action_lint(params)
        elif args.action == "fix":
            result = action_fix(params)
        else:
            result = {"status": "error", "message": f"Unknown action: {args.action}"}

        print(json.dumps(result, indent=2))
    elif args.file:
        with open(args.file, 'r') as f:
            content = f.read()
        fixed = lint_and_fix(content)
        with open(args.file, 'w') as f:
            f.write(fixed)
        print(f"Fixed: {args.file}")
    elif args.text:
        print(lint_and_fix(args.text))
    else:
        content = sys.stdin.read()
        print(lint_and_fix(content))
