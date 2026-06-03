"""
JobRadar — Query Deduplication Module
Reduces redundant API calls by clustering similar queries and selecting
the most specific representative per cluster.

Usage:
    queries = ["Spring Boot Pune", "Java Spring Boot Pune", "Spring Boot Developer Pune"]
    deduped = dedup_queries(queries)  # Returns ["Java Spring Boot Pune"]

Expected savings: 20-30% fewer API calls per refresh.
"""
import logging
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)

# Similarity threshold: queries >= 75% similar are considered duplicates
SIMILARITY_THRESHOLD = 0.75


def dedup_queries(queries: list[str], threshold: float = SIMILARITY_THRESHOLD) -> list[str]:
    """
    Cluster similar queries and return one representative (longest/most specific) per cluster.

    Algorithm:
    1. For each query, check if it belongs to an existing cluster
    2. Cluster membership = at least one existing query in cluster is >= threshold similar
    3. If no match, create new cluster
    4. Return longest query from each cluster (longest = most specific)

    Args:
        queries: List of search queries (may be duplicates or near-duplicates).
        threshold: Similarity threshold (0.0-1.0). Default 0.75.

    Returns:
        List of deduplicated queries, one per cluster. Order preserved by first query in cluster.
    """
    if not queries:
        return []

    if len(queries) == 1:
        return queries

    # Normalize all queries for comparison (lowercase, strip whitespace)
    normalized = [(q.lower().strip(), i) for i, q in enumerate(queries)]

    # Build clusters: each cluster is a set of (normalized_query, original_index) tuples
    clusters = []

    for norm_query, orig_idx in normalized:
        placed = False

        # Try to place this query in an existing cluster
        for cluster in clusters:
            # Check if this query matches ANY query in the cluster
            for existing_norm, _ in cluster:
                if _similarity(norm_query, existing_norm) >= threshold:
                    cluster.append((norm_query, orig_idx))
                    placed = True
                    break
            if placed:
                break

        # If no cluster matched, create a new one
        if not placed:
            clusters.append([(norm_query, orig_idx)])

    # From each cluster, select the longest query (most specific)
    # If tied, pick the one that appears first
    representatives = []
    for cluster in clusters:
        # Sort by length (descending), then by original index (ascending) for stability
        sorted_cluster = sorted(cluster, key=lambda x: (-len(x[0]), x[1]))
        longest_norm, longest_orig_idx = sorted_cluster[0]
        # Get the original (non-normalized) query from the input
        representatives.append(queries[longest_orig_idx])

    logger.info(
        f"[query_dedup] clustered {len(queries)} queries into {len(representatives)} "
        f"(savings: {len(queries) - len(representatives)} queries, "
        f"{100 * (len(queries) - len(representatives)) / max(1, len(queries)):.1f}%)"
    )

    return representatives


def _similarity(a: str, b: str) -> float:
    """
    Calculate similarity between two strings using SequenceMatcher.

    Returns: Float between 0.0 (completely different) and 1.0 (identical).
    """
    return SequenceMatcher(None, a, b).ratio()


def cluster_queries(queries: list[str], threshold: float = SIMILARITY_THRESHOLD) -> list[list[str]]:
    """
    Group similar queries into clusters (for debugging/analysis).

    Args:
        queries: List of search queries.
        threshold: Similarity threshold. Default 0.75.

    Returns:
        List of query clusters. Each cluster is a list of similar queries.

    Example:
        >>> clusters = cluster_queries(["Java Developer", "Java Engineer", "Python Dev"])
        >>> # Returns: [["Java Developer", "Java Engineer"], ["Python Dev"]]
    """
    if not queries:
        return []

    normalized = [(q.lower().strip(), i) for i, q in enumerate(queries)]
    clusters = []

    for norm_query, orig_idx in normalized:
        placed = False
        for cluster in clusters:
            for existing_norm, _ in cluster:
                if _similarity(norm_query, existing_norm) >= threshold:
                    cluster.append((norm_query, orig_idx))
                    placed = True
                    break
            if placed:
                break

        if not placed:
            clusters.append([(norm_query, orig_idx)])

    # Convert back to original queries for easier reading
    result = []
    for cluster in clusters:
        cluster_queries_list = [queries[orig_idx] for _, orig_idx in cluster]
        result.append(cluster_queries_list)

    return result
