"""
Response Sanitizer for execute_task Pipeline

Cleans tool responses by:
1. Stripping metadata fields (blocklist)
2. Unwrapping single-key wrapper objects
3. Flattening excessive nesting

Designed to be idempotent - already-clean responses pass through unchanged.
"""

# Blocklist of fields to strip (O(1) lookups)
STRIP_FIELDS = {
    # API junk
    'confidence', 'score', 'cursor', 'next_page', 'prev_page', 'pagination',
    'total_results', 'total_count', 'request_id', 'api_version',
    'rate_limit_remaining', 'rate_limit_reset', 'rate_limit_limit',
    # Wrapper metadata
    '_meta', '_links', '_embedded', 'meta', 'links', 'sources', 'source',
    'verification_status', 'verification_score', 'position_type',
    # Debug fields
    'debug', 'trace', 'request_time', 'response_time', 'elapsed_ms'
}

# Fields that indicate metadata context (created_at stripped only inside these)
METADATA_CONTEXT_FIELDS = {'_meta', 'meta', 'metadata', '_links', 'links'}

# Wrapper keys to unwrap when they're the only key
WRAPPER_KEYS = {'data', 'response', 'result', 'output', 'body', 'payload'}

# Keys that should NOT be unwrapped even if they're the only key
PRESERVE_SINGLE_KEYS = {'entries', 'status', 'error', 'message'}


def _strip_metadata_fields(obj, in_metadata_context=False):
    """
    Recursively remove blocklisted fields from response.

    Args:
        obj: The object to clean
        in_metadata_context: Whether we're inside a metadata-like object

    Returns:
        Cleaned object
    """
    if isinstance(obj, dict):
        result = {}
        for key, value in obj.items():
            # Skip blocklisted fields
            if key in STRIP_FIELDS:
                continue
            # Skip created_at only when in metadata context
            if key == 'created_at' and in_metadata_context:
                continue

            # Check if entering metadata context
            entering_metadata = key in METADATA_CONTEXT_FIELDS
            result[key] = _strip_metadata_fields(value, in_metadata_context or entering_metadata)
        return result

    elif isinstance(obj, list):
        return [_strip_metadata_fields(item, in_metadata_context) for item in obj]

    else:
        return obj


def _unwrap_single_key_wrappers(obj, depth=0, max_depth=3):
    """
    Unwrap single-key wrapper objects.

    Rules:
    - Only unwrap if single key is in WRAPPER_KEYS
    - Do NOT unwrap if key is in PRESERVE_SINGLE_KEYS
    - Do NOT unwrap if value is not dict or list
    - Max 3 levels deep to prevent infinite loops

    Args:
        obj: The object to unwrap
        depth: Current recursion depth
        max_depth: Maximum recursion depth

    Returns:
        Unwrapped object
    """
    if depth >= max_depth:
        return obj

    if isinstance(obj, dict):
        # Check for single-key wrapper pattern
        if len(obj) == 1:
            key = next(iter(obj))
            value = obj[key]

            # Only unwrap if it's a wrapper key and value is dict/list
            if key in WRAPPER_KEYS and key not in PRESERVE_SINGLE_KEYS:
                if isinstance(value, (dict, list)):
                    # Unwrap and continue recursively
                    return _unwrap_single_key_wrappers(value, depth + 1, max_depth)

        # Recursively process all values
        return {k: _unwrap_single_key_wrappers(v, depth + 1, max_depth) for k, v in obj.items()}

    elif isinstance(obj, list):
        return [_unwrap_single_key_wrappers(item, depth + 1, max_depth) for item in obj]

    else:
        return obj


def _flatten_deep_nesting(obj, max_depth=3, current_depth=0, prefix=''):
    """
    Flatten objects nested deeper than max_depth by joining keys with underscores.

    Rules:
    - Preserve arrays at any level
    - Preserve top-level structure
    - Only flatten deeply nested internal objects

    Args:
        obj: The object to flatten
        max_depth: Maximum allowed nesting depth before flattening
        current_depth: Current depth in the object
        prefix: Key prefix for flattened keys

    Returns:
        Flattened object
    """
    if isinstance(obj, list):
        # Preserve arrays, but process their contents
        return [_flatten_deep_nesting(item, max_depth, 0, '') for item in obj]

    elif isinstance(obj, dict):
        result = {}

        for key, value in obj.items():
            full_key = f"{prefix}_{key}" if prefix else key

            if isinstance(value, dict):
                if current_depth >= max_depth:
                    # We're too deep, flatten this dict
                    flattened = _flatten_dict_recursive(value, full_key)
                    result.update(flattened)
                else:
                    # Continue recursively
                    nested = _flatten_deep_nesting(value, max_depth, current_depth + 1, '')
                    if isinstance(nested, dict):
                        result[key] = nested
                    else:
                        result[key] = nested

            elif isinstance(value, list):
                # Preserve arrays
                result[key] = _flatten_deep_nesting(value, max_depth, current_depth, '')

            else:
                result[key] = value

        return result

    else:
        return obj


def _flatten_dict_recursive(obj, prefix):
    """
    Flatten a dict completely, joining all keys with underscores.

    Args:
        obj: Dict to flatten
        prefix: Key prefix

    Returns:
        Dict with flattened keys
    """
    result = {}

    if isinstance(obj, dict):
        for key, value in obj.items():
            full_key = f"{prefix}_{key}"

            if isinstance(value, dict):
                result.update(_flatten_dict_recursive(value, full_key))
            elif isinstance(value, list):
                # Preserve arrays as-is
                result[full_key] = value
            else:
                result[full_key] = value
    else:
        result[prefix] = obj

    return result


def sanitize_response(response):
    """
    Main entry point: sanitize a tool response.

    Applies three operations in order:
    1. Strip metadata fields (blocklist)
    2. Unwrap single-key wrapper objects
    3. Flatten excessive nesting

    Idempotent: already-clean responses pass through unchanged.

    Args:
        response: The response dict to sanitize

    Returns:
        Sanitized response dict
    """
    if not isinstance(response, dict):
        return response

    # Operation 1: Strip metadata fields
    result = _strip_metadata_fields(response)

    # Operation 2: Unwrap single-key wrappers
    result = _unwrap_single_key_wrappers(result)

    # Operation 3: Flatten excessive nesting
    result = _flatten_deep_nesting(result)

    return result
