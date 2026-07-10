# Full docstrings and function descriptions: data/orchestrate_docstrings.json

STRIP_FIELDS = {
    'confidence', 'score', 'cursor', 'next_page', 'prev_page', 'pagination',
    'total_results', 'total_count', 'request_id', 'api_version',
    'rate_limit_remaining', 'rate_limit_reset', 'rate_limit_limit',
    '_meta', '_links', '_embedded', 'meta', 'links',
    'verification_status', 'verification_score', 'position_type',
    'debug', 'trace', 'request_time', 'response_time', 'elapsed_ms'
}

METADATA_CONTEXT_FIELDS = {'_meta', 'meta', 'metadata', '_links', 'links'}

WRAPPER_KEYS = {'data', 'response', 'result', 'output', 'body', 'payload'}

PRESERVE_SINGLE_KEYS = {'entries', 'status', 'error', 'message'}

def _strip_metadata_fields(obj, in_metadata_context=False):
    if isinstance(obj, dict):
        result = {}
        for key, value in obj.items():
            if key in STRIP_FIELDS:
                continue
            if key == 'created_at' and in_metadata_context:
                continue

            entering_metadata = key in METADATA_CONTEXT_FIELDS
            result[key] = _strip_metadata_fields(value, in_metadata_context or entering_metadata)
        return result

    elif isinstance(obj, list):
        return [_strip_metadata_fields(item, in_metadata_context) for item in obj]

    else:
        return obj

def _unwrap_single_key_wrappers(obj, depth=0, max_depth=3):
    if depth >= max_depth:
        return obj

    if isinstance(obj, dict):
        if len(obj) == 1:
            key = next(iter(obj))
            value = obj[key]

            if key in WRAPPER_KEYS and key not in PRESERVE_SINGLE_KEYS:
                if isinstance(value, (dict, list)):
                    return _unwrap_single_key_wrappers(value, depth + 1, max_depth)

        return {k: _unwrap_single_key_wrappers(v, depth + 1, max_depth) for k, v in obj.items()}

    elif isinstance(obj, list):
        return [_unwrap_single_key_wrappers(item, depth + 1, max_depth) for item in obj]

    else:
        return obj

def _flatten_deep_nesting(obj, max_depth=3, current_depth=0, prefix=''):
    if isinstance(obj, list):
        return [_flatten_deep_nesting(item, max_depth, 0, '') for item in obj]

    elif isinstance(obj, dict):
        result = {}

        for key, value in obj.items():
            full_key = f"{prefix}_{key}" if prefix else key

            if isinstance(value, dict):
                if current_depth >= max_depth:
                    flattened = _flatten_dict_recursive(value, full_key)
                    result.update(flattened)
                else:
                    nested = _flatten_deep_nesting(value, max_depth, current_depth + 1, '')
                    if isinstance(nested, dict):
                        result[key] = nested
                    else:
                        result[key] = nested

            elif isinstance(value, list):
                result[key] = _flatten_deep_nesting(value, max_depth, current_depth, '')

            else:
                result[key] = value

        return result

    else:
        return obj

def _flatten_dict_recursive(obj, prefix):
    result = {}

    if isinstance(obj, dict):
        for key, value in obj.items():
            full_key = f"{prefix}_{key}"

            if isinstance(value, dict):
                result.update(_flatten_dict_recursive(value, full_key))
            elif isinstance(value, list):
                result[full_key] = value
            else:
                result[full_key] = value
    else:
        result[prefix] = obj

    return result

def sanitize_response(response):
    if not isinstance(response, dict):
        return response

    result = _strip_metadata_fields(response)

    result = _unwrap_single_key_wrappers(result)

    result = _flatten_deep_nesting(result)

    return result
