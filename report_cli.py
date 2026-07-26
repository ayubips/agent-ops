import sys
from src.observability import get_connection


def print_overview(conn):
    row = conn.execute("""
        SELECT
            COUNT(*) as total_runs,
            SUM(CASE WHEN final_status = 'success' THEN 1 ELSE 0 END) as successes,
            SUM(CASE WHEN final_status = 'failed' THEN 1 ELSE 0 END) as failures
        FROM runs
    """).fetchone()

    cost_row = conn.execute("""
        SELECT SUM(cost_usd) as total_cost, SUM(tokens_used) as total_tokens
        FROM steps WHERE step_name = 'synthesize'
    """).fetchone()

    fallback_row = conn.execute("""
        SELECT COUNT(*) as fallback_count FROM steps
        WHERE step_name = 'synthesize' AND error LIKE 'used fallback%'
    """).fetchone()

    total = row["total_runs"] or 0
    successes = row["successes"] or 0
    success_rate = (successes / total * 100) if total else 0
    total_cost = cost_row["total_cost"] or 0
    total_tokens = cost_row["total_tokens"] or 0

    print("=" * 50)
    print("OVERVIEW")
    print("=" * 50)
    print(f"Total runs:       {total}")
    print(f"Success rate:     {success_rate:.1f}% ({successes}/{total})")
    print(f"Failures:         {row['failures'] or 0}")
    print(f"Fallback used:    {fallback_row['fallback_count'] or 0} times")
    print(f"Total tokens:     {total_tokens:,}")
    print(f"Total cost:       ${total_cost:.6f}")
    print()


def print_step_breakdown(conn):
    rows = conn.execute("""
        SELECT
            step_name,
            COUNT(*) as calls,
            AVG(latency_ms) as avg_latency,
            SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failures
        FROM steps
        GROUP BY step_name
        ORDER BY step_name
    """).fetchall()

    print("=" * 50)
    print("PER-STEP BREAKDOWN")
    print("=" * 50)
    print(f"{'Step':<15}{'Calls':<10}{'Avg Latency':<15}{'Failures':<10}")
    for r in rows:
        print(f"{r['step_name']:<15}{r['calls']:<10}{r['avg_latency']:.0f}ms{'':<9}{r['failures']:<10}")
    print()


def print_recent_runs(conn, limit=10):
    rows = conn.execute("""
        SELECT run_id, query, final_status, started_at
        FROM runs
        ORDER BY started_at DESC
        LIMIT ?
    """, (limit,)).fetchall()

    print("=" * 50)
    print(f"RECENT RUNS (last {limit})")
    print("=" * 50)
    for r in rows:
        query_short = (r["query"][:40] + "...") if len(r["query"]) > 40 else r["query"]
        print(f"[{r['final_status']:<8}] {query_short:<43} {r['started_at'][:19]}")
    print()


def main():
    limit = 10
    if len(sys.argv) > 1:
        try:
            limit = int(sys.argv[1])
        except ValueError:
            print("Usage: python report_cli.py [number_of_recent_runs]")
            sys.exit(1)

    with get_connection() as conn:
        print_overview(conn)
        print_step_breakdown(conn)
        print_recent_runs(conn, limit=limit)


if __name__ == "__main__":
    main()