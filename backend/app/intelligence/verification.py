def determine_corroboration_level(source_count):
    count = max(0, int(source_count or 0))
    if count <= 1:
        return "single"
    if count >= 4:
        return "strong"
    return "corroborated"
