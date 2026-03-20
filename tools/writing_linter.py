#!/usr/bin/env python3
"""
writing_linter.py - Auto-fix common AI writing pattern errors

Actions:
- lint: Detects and auto-fixes AI writing patterns in text
- lint_file: Runs lint() on a file, saves fixed version in place
"""

import argparse
import json
import os
import re
from typing import Tuple, List, Dict


def detect_tricolon(text: str) -> List[Dict]:
    """
    Detect tricolon patterns: 'a real X, a real Y, a real Z' or similar
    three parallel clauses with repeated lead word.

    Also detects AI slop pattern: article + gerund/noun repeated 3+ times
    e.g., "the typing, the arranging, the formatting, the editing"
    """
    violations = []

    # Pattern: repeated word followed by different noun/phrase, three times
    # Examples: "a real X, a real Y, a real Z" / "every X, every Y, every Z"
    patterns = [
        # "a X, a Y, a Z" pattern
        r'\b(a|an|the|every|each|no|when|if|that|this)\s+(\w+)\s+(\w+(?:\s+\w+)*),\s+\1\s+(\w+)\s+(\w+(?:\s+\w+)*),\s+\1\s+(\w+)\s+(\w+(?:\s+\w+)*)',
        # Simpler pattern for "word X, word Y, word Z"
        r'\b(every|each|no|every|when)\s+(\w+),\s+\1\s+(\w+),\s+\1\s+(\w+)',
    ]

    for pattern in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            violations.append({
                "type": "tricolon",
                "match": match.group(0),
                "start": match.start(),
                "end": match.end()
            })

    # AI slop pattern: article + single word, repeated 3+ times with commas
    # Catches: "the typing, the arranging, the formatting" (AI enumeration slop)
    # Excludes: "the good, the bad, and the ugly" (proper cultural reference)
    article_enum_pattern = r'\b(the|a|an)\s+(\w+)(?:,\s+\1\s+(\w+)){2,}'

    for match in re.finditer(article_enum_pattern, text, re.IGNORECASE):
        matched_text = match.group(0)

        # Skip known proper references (cultural tricolons that are acceptable)
        proper_refs = [
            "the good, the bad, and the ugly",
            "the good, the bad and the ugly",
            "the father, the son, and the holy",
            "the past, the present, and the future",
        ]
        if any(ref in matched_text.lower() for ref in proper_refs):
            continue

        # Skip if it ends with "and the X" (proper enumeration ending)
        # but only if it's exactly 3 items (classic tricolon is fine)
        items = re.findall(r'\b(?:the|a|an)\s+(\w+)', matched_text, re.IGNORECASE)
        if len(items) == 3 and ", and " in matched_text.lower():
            continue

        violations.append({
            "type": "tricolon_article_enum",
            "match": matched_text,
            "start": match.start(),
            "end": match.end()
        })

    return violations


def fix_tricolon(text: str) -> Tuple[str, List[str]]:
    """Fix tricolon patterns by keeping the strongest element or collapsing enumeration."""
    changes = []

    # Pattern: "a real X, a real Y, a real Z"
    pattern1 = r'\b(a|an)\s+(real|true|genuine)\s+(\w+(?:\s+\w+)*),\s+\1\s+\2\s+(\w+(?:\s+\w+)*),\s+\1\s+\2\s+(\w+(?:\s+\w+)*)'

    def replace_real_pattern(m):
        lead = m.group(1)
        adj = m.group(2)
        # Keep the last element (often most important)
        third = m.group(5)
        changes.append(f"Tricolon: '{m.group(0)}' → '{lead} {adj} {third}'")
        return f"{lead} {adj} {third}"

    text = re.sub(pattern1, replace_real_pattern, text, flags=re.IGNORECASE)

    # Pattern: "every X, every Y, every Z"
    pattern2 = r'\b(every|each)\s+(\w+),\s+\1\s+(\w+),\s+\1\s+(\w+)'

    def replace_every_pattern(m):
        lead = m.group(1)
        # Combine into "every X, Y, and Z" which is cleaner
        first, second, third = m.group(2), m.group(3), m.group(4)
        replacement = f"{lead} {first}, {second}, and {third}"
        changes.append(f"Tricolon: '{m.group(0)}' → '{replacement}'")
        return replacement

    text = re.sub(pattern2, replace_every_pattern, text, flags=re.IGNORECASE)

    # AI slop pattern: article + single word, repeated 3+ times
    # "the typing, the arranging, the formatting, the editing" → "typing, arranging, formatting, and editing"
    article_enum_pattern = r'\b(the|a|an)\s+(\w+)(?:,\s+\1\s+(\w+)){2,}'

    def replace_article_enum(m):
        matched_text = m.group(0)

        # Skip known proper references
        proper_refs = [
            "the good, the bad, and the ugly",
            "the good, the bad and the ugly",
            "the father, the son, and the holy",
            "the past, the present, and the future",
        ]
        if any(ref in matched_text.lower() for ref in proper_refs):
            return matched_text

        # Skip if it's a clean 3-item with "and" (acceptable tricolon)
        items = re.findall(r'\b(?:the|a|an)\s+(\w+)', matched_text, re.IGNORECASE)
        if len(items) == 3 and ", and " in matched_text.lower():
            return matched_text

        # Extract just the words without articles
        if len(items) >= 3:
            # Collapse: remove repeated articles, make clean list
            if len(items) == 3:
                replacement = f"{items[0]}, {items[1]}, and {items[2]}"
            else:
                # 4+ items: join all but last with commas, then "and" before last
                replacement = ", ".join(items[:-1]) + f", and {items[-1]}"

            changes.append(f"Article enumeration: '{matched_text}' → '{replacement}'")
            return replacement

        return matched_text

    text = re.sub(article_enum_pattern, replace_article_enum, text, flags=re.IGNORECASE)

    return text, changes


def detect_fragments(text: str) -> List[Dict]:
    """
    Detect incomplete sentence fragments used as emphasis.
    Sentences under 6 words with no verb.
    Also detects dramatic single-word adverbs used as standalone sentences.
    """
    violations = []

    # Dramatic single-word adverbs used as standalone sentences (AI emphasis pattern)
    dramatic_adverbs = {
        'permanently', 'irreversibly', 'completely', 'absolutely', 'fundamentally',
        'entirely', 'totally', 'utterly', 'instantly', 'immediately', 'finally',
        'ultimately', 'inevitably', 'constantly', 'continuously', 'endlessly',
        'relentlessly', 'ruthlessly', 'mercilessly', 'systematically', 'deliberately',
        'intentionally', 'purposefully', 'strategically', 'dramatically', 'radically',
        'profoundly', 'deeply', 'massively', 'exponentially', 'explosively'
    }

    # Common verbs to check for (expanded list)
    verbs = {'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had',
             'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might',
             'must', 'shall', 'can', 'need', 'make', 'made', 'take', 'took', 'get',
             'got', 'give', 'gave', 'go', 'went', 'come', 'came', 'see', 'saw',
             'know', 'knew', 'think', 'thought', 'say', 'said', 'tell', 'told',
             'run', 'ran', 'write', 'wrote', 'read', 'find', 'found', 'want',
             'use', 'used', 'work', 'worked', 'try', 'tried', 'ask', 'asked',
             'generate', 'generates', 'generated', 'creates', 'becomes',
             # Additional common verbs to reduce false positives
             'rebuild', 'rebuilt', 'collapse', 'collapsed', 'break', 'broke', 'broken',
             'build', 'built', 'start', 'started', 'stop', 'stopped', 'end', 'ended',
             'begin', 'began', 'begun', 'finish', 'finished', 'complete', 'completed',
             'change', 'changed', 'move', 'moved', 'turn', 'turned', 'set', 'put',
             'keep', 'kept', 'let', 'help', 'helped', 'show', 'showed', 'shown',
             'call', 'called', 'feel', 'felt', 'seem', 'seemed', 'leave', 'left',
             'mean', 'meant', 'bring', 'brought', 'lead', 'led', 'understand',
             'understood', 'watch', 'watched', 'follow', 'followed', 'learn', 'learned',
             'meet', 'met', 'include', 'included', 'continue', 'continued', 'happen',
             'happened', 'hold', 'held', 'live', 'lived', 'stand', 'stood', 'lose',
             'lost', 'pay', 'paid', 'send', 'sent', 'expect', 'expected', 'build',
             'create', 'created', 'fail', 'failed', 'succeed', 'succeeded', 'grow',
             'grew', 'grown', 'open', 'opened', 'close', 'closed', 'win', 'won',
             'offer', 'offered', 'remember', 'remembered', 'consider', 'considered',
             'appear', 'appeared', 'buy', 'bought', 'serve', 'served', 'die', 'died',
             'require', 'required', 'suggest', 'suggested', 'raise', 'raised', 'pass',
             'passed', 'sell', 'sold', 'add', 'added', 'decide', 'decided', 'return',
             'returned', 'explain', 'explained', 'develop', 'developed', 'carry',
             'carried', 'remain', 'remained', 'involve', 'involved', 'receive', 'received',
             'notice', 'noticed', 'notices', 'happen', 'happens', 'love', 'loved', 'loves',
             'hate', 'hated', 'hates', 'believe', 'believed', 'believes', 'realize',
             'realized', 'realizes', 'achieve', 'achieved', 'achieves', 'discover',
             'discovered', 'discovers', 'prove', 'proved', 'proves', 'proven', 'solve',
             'solved', 'solves', 'cause', 'caused', 'causes', 'allow', 'allowed', 'allows',
             'prevent', 'prevented', 'prevents', 'produce', 'produced', 'produces',
             'provide', 'provided', 'provides', 'support', 'supported', 'supports',
             'accept', 'accepted', 'accepts', 'agree', 'agreed', 'agrees', 'argue',
             'argued', 'argues', 'assume', 'assumed', 'assumes', 'claim', 'claimed',
             'claims', 'confirm', 'confirmed', 'confirms', 'deny', 'denied', 'denies',
             'doubt', 'doubted', 'doubts', 'ensure', 'ensured', 'ensures', 'guarantee',
             'guaranteed', 'guarantees', 'hope', 'hoped', 'hopes', 'ignore', 'ignored',
             'ignores', 'imply', 'implied', 'implies', 'indicate', 'indicated', 'indicates',
             'mention', 'mentioned', 'mentions', 'note', 'noted', 'notes', 'point',
             'pointed', 'points', 'prefer', 'preferred', 'prefers', 'propose', 'proposed',
             'proposes', 'recommend', 'recommended', 'recommends', 'refuse', 'refused',
             'refuses', 'report', 'reported', 'reports', 'reveal', 'revealed', 'reveals',
             'state', 'stated', 'states', 'warn', 'warned', 'warns'}

    # Split by sentence-ending punctuation (handles multiple spaces too)
    sentences = re.split(r'(?<=[.!?])\s+', text)

    for i, sentence in enumerate(sentences):
        stripped = sentence.strip()
        words = stripped.rstrip('.!?').split()
        word_count = len(words)

        # Check for single-word dramatic adverb sentences
        if word_count == 1:
            word = words[0].lower()
            if word in dramatic_adverbs:
                violations.append({
                    "type": "dramatic_adverb",
                    "text": stripped,
                    "index": i
                })
                continue

        if 1 <= word_count <= 5:
            # Check if any word is a verb
            lower_words = {w.lower() for w in words}
            has_verb = bool(lower_words & verbs)

            if not has_verb:
                violations.append({
                    "type": "fragment",
                    "text": stripped,
                    "index": i
                })

    return violations


def fix_fragments(text: str) -> Tuple[str, List[str]]:
    """
    DELETE consecutive verbless fragments (1-3 words, no verb, 2+ in a row).
    These are not sentences. They add nothing. Just strip them out.

    Examples:
    - "The system broke. Fast. Permanently. Irreversibly. We rebuilt." → "The system broke. We rebuilt."
    - "Pure chaos. Total disaster. No recovery." → deleted entirely
    """
    changes = []

    # Split by sentence-ending punctuation
    sentences = re.split(r'(?<=[.!?])\s+', text)

    # Expanded verb list (must match detect_fragments)
    verbs = {'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had',
             'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might',
             'must', 'shall', 'can', 'need', 'make', 'made', 'take', 'took', 'get',
             'got', 'give', 'gave', 'go', 'went', 'come', 'came', 'see', 'saw',
             'know', 'knew', 'think', 'thought', 'say', 'said', 'tell', 'told',
             'run', 'ran', 'write', 'wrote', 'read', 'find', 'found', 'want',
             'use', 'used', 'work', 'worked', 'try', 'tried', 'ask', 'asked',
             'generate', 'generates', 'generated', 'creates', 'becomes',
             'rebuild', 'rebuilt', 'collapse', 'collapsed', 'break', 'broke', 'broken',
             'build', 'built', 'start', 'started', 'stop', 'stopped', 'end', 'ended',
             'begin', 'began', 'begun', 'finish', 'finished', 'complete', 'completed',
             'change', 'changed', 'move', 'moved', 'turn', 'turned', 'set', 'put',
             'keep', 'kept', 'let', 'help', 'helped', 'show', 'showed', 'shown',
             'call', 'called', 'feel', 'felt', 'seem', 'seemed', 'leave', 'left',
             'mean', 'meant', 'bring', 'brought', 'lead', 'led', 'understand',
             'understood', 'watch', 'watched', 'follow', 'followed', 'learn', 'learned',
             'meet', 'met', 'include', 'included', 'continue', 'continued', 'happen',
             'happened', 'hold', 'held', 'live', 'lived', 'stand', 'stood', 'lose',
             'lost', 'pay', 'paid', 'send', 'sent', 'expect', 'expected', 'build',
             'create', 'created', 'fail', 'failed', 'succeed', 'succeeded', 'grow',
             'grew', 'grown', 'open', 'opened', 'close', 'closed', 'win', 'won',
             'offer', 'offered', 'remember', 'remembered', 'consider', 'considered',
             'appear', 'appeared', 'buy', 'bought', 'serve', 'served', 'die', 'died',
             'require', 'required', 'suggest', 'suggested', 'raise', 'raised', 'pass',
             'passed', 'sell', 'sold', 'add', 'added', 'decide', 'decided', 'return',
             'returned', 'explain', 'explained', 'develop', 'developed', 'carry',
             'carried', 'remain', 'remained', 'involve', 'involved', 'receive', 'received',
             'notice', 'noticed', 'notices', 'happen', 'happens', 'love', 'loved', 'loves',
             'hate', 'hated', 'hates', 'believe', 'believed', 'believes', 'realize',
             'realized', 'realizes', 'achieve', 'achieved', 'achieves', 'discover',
             'discovered', 'discovers', 'prove', 'proved', 'proves', 'proven', 'solve',
             'solved', 'solves', 'cause', 'caused', 'causes', 'allow', 'allowed', 'allows',
             'prevent', 'prevented', 'prevents', 'produce', 'produced', 'produces',
             'provide', 'provided', 'provides', 'support', 'supported', 'supports',
             'accept', 'accepted', 'accepts', 'agree', 'agreed', 'agrees', 'argue',
             'argued', 'argues', 'assume', 'assumed', 'assumes', 'claim', 'claimed',
             'claims', 'confirm', 'confirmed', 'confirms', 'deny', 'denied', 'denies',
             'doubt', 'doubted', 'doubts', 'ensure', 'ensured', 'ensures', 'guarantee',
             'guaranteed', 'guarantees', 'hope', 'hoped', 'hopes', 'ignore', 'ignored',
             'ignores', 'imply', 'implied', 'implies', 'indicate', 'indicated', 'indicates',
             'mention', 'mentioned', 'mentions', 'note', 'noted', 'notes', 'point',
             'pointed', 'points', 'prefer', 'preferred', 'prefers', 'propose', 'proposed',
             'proposes', 'recommend', 'recommended', 'recommends', 'refuse', 'refused',
             'refuses', 'report', 'reported', 'reports', 'reveal', 'revealed', 'reveals',
             'state', 'stated', 'states', 'warn', 'warned', 'warns'}

    # Prepositions that make following words function as nouns, not verbs
    prepositions = {'without', 'with', 'for', 'by', 'of', 'in', 'on', 'at', 'to', 'from'}

    def is_verbless_fragment(sentence_text: str) -> bool:
        """Check if sentence is a verbless fragment (1-3 words, no functioning verb)."""
        stripped = sentence_text.strip()
        words = stripped.rstrip('.!?').split()
        word_count = len(words)

        # Only 1-3 word sentences qualify as deletable fragments
        if not (1 <= word_count <= 3):
            return False

        # Check for verbs, but exclude words that follow prepositions
        # (e.g., "without fail" - "fail" is a noun here, not a verb)
        has_functioning_verb = False
        for i, word in enumerate(words):
            lower_word = word.lower()
            if lower_word in verbs:
                # Check if preceded by a preposition (making it a noun)
                if i > 0 and words[i-1].lower() in prepositions:
                    continue  # This is a noun, not a verb
                has_functioning_verb = True
                break

        return not has_functioning_verb

    # Find consecutive fragments (2+ in a row)
    fragment_runs = []
    current_run = []

    for i, sentence in enumerate(sentences):
        if is_verbless_fragment(sentence):
            current_run.append((i, sentence.strip()))
        else:
            if len(current_run) >= 2:
                fragment_runs.append(current_run)
            current_run = []

    # Handle last run
    if len(current_run) >= 2:
        fragment_runs.append(current_run)

    # Process runs in reverse order to maintain indices
    result_sentences = sentences.copy()

    for run in reversed(fragment_runs):
        if len(run) >= 2:
            # Get indices to delete
            start_idx = run[0][0]
            end_idx = run[-1][0]

            deleted_text = " ".join([s[1] for s in run])
            changes.append(f"Deleted fragments: '{deleted_text}'")

            # Delete the range entirely
            del result_sentences[start_idx:end_idx + 1]

    return " ".join(result_sentences), changes


def detect_ai_transition_words(text: str) -> List[Dict]:
    """
    Detect AI transition words/phrases at the start of sentences.
    These are telltale signs of AI-generated text.
    """
    violations = []

    # AI transition words/phrases that commonly start sentences
    ai_transitions = [
        'moreover', 'furthermore', 'additionally', 'in conclusion',
        'it is worth noting', 'it should be noted', 'delve', 'leverage',
        'utilize', 'tapestry', 'landscape'
    ]

    # Split by sentence-ending punctuation
    sentences = re.split(r'(?<=[.!?])\s+', text)

    for i, sentence in enumerate(sentences):
        stripped = sentence.strip()
        lower_sentence = stripped.lower()

        for transition in ai_transitions:
            # Check if sentence starts with this transition
            if lower_sentence.startswith(transition):
                # Get the actual word from the original (preserve case)
                actual_word = stripped[:len(transition)]
                violations.append({
                    "type": "ai_transition",
                    "word": actual_word,
                    "sentence": stripped,
                    "index": i
                })
                break  # Only flag once per sentence

    return violations


def flag_ai_transitions(text: str) -> Tuple[str, List[str]]:
    """
    Detect AI transition words and add warnings to change_log.
    Does NOT modify text - returns unchanged.
    """
    warnings = []

    violations = detect_ai_transition_words(text)
    for v in violations:
        warnings.append(f"AI WORD WARNING: sentence starts with '{v['word']}'")

    # Return text UNCHANGED, with warnings only
    return text, warnings


def lint(text: str) -> Dict:
    """
    Detect and auto-fix AI writing patterns.

    Patterns detected:
    1. TRICOLON - comma-separated parallel lists with repeated lead word (auto-fixed)
    2. CONSECUTIVE VERBLESS FRAGMENTS - 2+ consecutive 1-3 word sentences with no verb (auto-deleted)
    3. AI TRANSITION WORDS - telltale AI phrases at sentence start (flagged only)

    Returns:
        dict with 'fixed_text', 'change_log', and 'violations_found'
    """
    change_log = []
    violations_found = []

    # Detect violations first
    tricolon_violations = detect_tricolon(text)
    fragment_violations = detect_fragments(text)
    ai_transition_violations = detect_ai_transition_words(text)

    for v in tricolon_violations:
        violations_found.append(f"TRICOLON: {v['match']}")

    for v in fragment_violations:
        if v['type'] == 'dramatic_adverb':
            violations_found.append(f"DRAMATIC_ADVERB: {v['text']}")
        else:
            violations_found.append(f"FRAGMENT: {v['text']}")

    for v in ai_transition_violations:
        violations_found.append(f"AI_TRANSITION: {v['word']}")

    # Apply fixes
    fixed_text = text

    # Fix tricolons (auto-fix)
    fixed_text, tricolon_changes = fix_tricolon(fixed_text)
    change_log.extend(tricolon_changes)

    # Fix fragments (auto-delete consecutive verbless fragments)
    fixed_text, fragment_changes = fix_fragments(fixed_text)
    change_log.extend(fragment_changes)

    # Detect AI transitions (flag only, no modification)
    _, ai_warnings = flag_ai_transitions(fixed_text)
    change_log.extend(ai_warnings)

    return {
        "status": "success",
        "original_text": text,
        "fixed_text": fixed_text,
        "change_log": change_log,
        "violations_found": violations_found,
        "patterns_fixed": len([c for c in change_log if not c.startswith('AI WORD WARNING')])
    }


def lint_file(filepath: str) -> Dict:
    """
    Run lint() on a file and save the fixed version in place.

    Args:
        filepath: Path to the file to lint

    Returns:
        dict with result of linting and file operation status
    """
    # Handle relative paths
    if not os.path.isabs(filepath):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        filepath = os.path.join(base_dir, filepath)

    if not os.path.exists(filepath):
        return {
            "status": "error",
            "error": f"File not found: {filepath}"
        }

    try:
        with open(filepath, 'r') as f:
            original_text = f.read()

        result = lint(original_text)

        if result["status"] == "success" and result["patterns_fixed"] > 0:
            with open(filepath, 'w') as f:
                f.write(result["fixed_text"])

            result["file_updated"] = True
            result["filepath"] = filepath
        else:
            result["file_updated"] = False
            result["filepath"] = filepath

        # Remove original_text from response to reduce output size
        del result["original_text"]

        return result

    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "filepath": filepath
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Writing linter for AI pattern detection and fixing")
    parser.add_argument("action", help="Action to perform: lint, lint_file")
    parser.add_argument("--params", type=str, help="JSON params")
    parser.add_argument("--text", type=str, help="Text to lint (for lint action)")
    parser.add_argument("--filepath", type=str, help="File path (for lint_file action)")

    args = parser.parse_args()

    params = json.loads(args.params) if args.params else {}

    # Allow params to override command line args
    text = params.get("text", args.text)
    filepath = params.get("filepath", args.filepath)

    if args.action == "lint":
        if not text:
            print(json.dumps({"status": "error", "error": "text parameter required"}))
        else:
            result = lint(text)
            print(json.dumps(result, indent=2))

    elif args.action == "lint_file":
        if not filepath:
            print(json.dumps({"status": "error", "error": "filepath parameter required"}))
        else:
            result = lint_file(filepath)
            print(json.dumps(result, indent=2))

    else:
        print(json.dumps({
            "status": "error",
            "error": f"Unknown action: {args.action}",
            "available_actions": ["lint", "lint_file"]
        }))
