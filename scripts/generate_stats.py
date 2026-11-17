#!/usr/bin/env python3
"""Generate self-hosted GitHub Stats & Most Used Languages SVG cards (Radical theme)."""
import html
import json
import math
import os
import subprocess
import sys
import urllib.request

USERNAME = os.environ.get("GITHUB_USER", "ExeDevCentral")
OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")


def get_token() -> str:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        return token.strip()
    try:
        return subprocess.check_output(["gh", "auth", "token"], text=True).strip()
    except Exception as exc:
        raise RuntimeError("Missing GITHUB_TOKEN / gh auth token") from exc


def graphql(token: str, query: str, variables: dict | None = None) -> dict:
    payload = json.dumps({"query": query, "variables": variables or {}}).encode("utf-8")
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=payload,
        headers={
            "Authorization": f"bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "ExeDevCentral-Stats-Generator",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if "errors" in data:
        raise RuntimeError(f"GraphQL error: {data['errors']}")
    return data["data"]


def fetch_stats(token: str, login: str) -> dict:
    base_q = """
    query($login: String!) {
      user(login: $login) {
        followers { totalCount }
        contributionsCollection {
          contributionYears
        }
      }
    }
    """
    base = graphql(token, base_q, {"login": login})["user"]
    years = base["contributionsCollection"]["contributionYears"]
    followers = base["followers"]["totalCount"]

    total_commits = 0
    total_prs = 0
    total_issues = 0
    total_contribs = 0

    year_q = """
    query($login: String!, $from: DateTime!, $to: DateTime!) {
      user(login: $login) {
        contributionsCollection(from: $from, to: $to) {
          totalCommitContributions
          totalPullRequestContributions
          totalIssueContributions
          restrictedContributionsCount
          contributionCalendar { totalContributions }
        }
      }
    }
    """
    for yr in years:
        ydata = graphql(
            token,
            year_q,
            {
                "login": login,
                "from": f"{yr}-01-01T00:00:00Z",
                "to": f"{yr}-12-31T23:59:59Z",
            },
        )["user"]["contributionsCollection"]
        total_commits += ydata["totalCommitContributions"] + ydata["restrictedContributionsCount"]
        total_prs += ydata["totalPullRequestContributions"]
        total_issues += ydata["totalIssueContributions"]
        total_contribs += ydata["contributionCalendar"]["totalContributions"]

    # Paginate owned non-fork repositories
    repos_q = """
    query($login: String!, $after: String) {
      user(login: $login) {
        repositories(first: 100, after: $after, ownerAffiliations: OWNER, isFork: false) {
          totalCount
          pageInfo { hasNextPage endCursor }
          nodes {
            stargazerCount
            forkCount
            languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
              edges {
                size
                node { name color }
              }
            }
          }
        }
      }
    }
    """
    total_stars = 0
    total_repos = 0
    lang_totals: dict[str, dict] = {}
    after = None

    while True:
        rdata = graphql(token, repos_q, {"login": login, "after": after})["user"]["repositories"]
        total_repos = rdata["totalCount"]
        for repo in rdata["nodes"]:
            total_stars += repo["stargazerCount"]
            for edge in repo["languages"]["edges"]:
                name = edge["node"]["name"]
                color = edge["node"]["color"] or "#a9fef7"
                size = edge["size"]
                if name not in lang_totals:
                    lang_totals[name] = {"size": 0, "color": color}
                lang_totals[name]["size"] += size
        if not rdata["pageInfo"]["hasNextPage"]:
            break
        after = rdata["pageInfo"]["endCursor"]

    return {
        "login": login,
        "stars": total_stars,
        "commits": total_commits,
        "contributions": total_contribs,
        "prs": total_prs,
        "issues": total_issues,
        "repos": total_repos,
        "followers": followers,
        "languages": lang_totals,
    }


def compute_rank(stats: dict) -> tuple[str, float]:
    score = (
        stats["commits"] * 0.45
        + stats["stars"] * 4.0
        + stats["prs"] * 3.0
        + stats["issues"] * 1.5
        + stats["followers"] * 1.2
        + stats["repos"] * 2.0
    )
    if score >= 1500:
        return "S", 0.92
    if score >= 900:
        return "A+", 0.85
    if score >= 500:
        return "A", 0.78
    if score >= 250:
        return "B+", 0.68
    return "B", 0.55


def render_stats_svg(stats: dict) -> str:
    rank, pct = compute_rank(stats)
    r = 40
    circ = 2 * math.pi * r
    dash_offset = circ * (1.0 - pct)

    rows = [
        ("Total Stars", f"{stats['stars']:,}", "M8 .25a.75.75 0 01.673.418l1.882 3.815 4.21.612a.75.75 0 01.416 1.279l-3.046 2.97.719 4.192a.75.75 0 01-1.088.791L8 12.347l-3.766 1.98a.75.75 0 01-1.088-.79l.72-4.194L.818 6.374a.75.75 0 01.416-1.28l4.21-.611L7.327.668A.75.75 0 018 .25z"),
        ("Total Commits", f"{stats['commits']:,}", "M10.5 7.75a2.5 2.5 0 11-5 0 2.5 2.5 0 015 0zm1.43.75a4.002 4.002 0 01-7.86 0H.75a.75.75 0 110-1.5h3.32a4.001 4.001 0 017.86 0h3.32a.75.75 0 110 1.5h-3.32z"),
        ("Total PRs", f"{stats['prs']:,}", "M7.177 3.073L9.573.677A.25.25 0 0110 .854v4.792a.25.25 0 01-.427.177L7.177 3.427a.25.25 0 010-.354zM3.75 2.5a.75.75 0 100 1.5.75.75 0 000-1.5zm-2.25.75a2.25 2.25 0 113 2.122v5.256a2.251 2.251 0 11-1.5 0V5.372A2.25 2.25 0 011.5 3.25zM11 2.5h-1V4h1a1 1 0 011 1v5.628a2.251 2.251 0 101.5 0V5A2.5 2.5 0 0011 2.5zm1 10.25a.75.75 0 111.5 0 .75.75 0 01-1.5 0zM3.75 12a.75.75 0 100 1.5.75.75 0 000-1.5z"),
        ("Repositories", f"{stats['repos']:,}", "M2 2.5A2.5 2.5 0 014.5 0h8.75a.75.75 0 01.75.75v12.5a.75.75 0 01-.75.75h-2.5a.75.75 0 110-1.5h1.75v-2h-8a1 1 0 00-.714 1.7.75.75 0 01-1.072 1.05A2.495 2.495 0 012 11.5v-9zm10.5-1V9h-8c-.356 0-.694.074-1 .208V2.5a1 1 0 011-1h8z"),
        ("Followers", f"{stats['followers']:,}", "M5.5 3.5a2 2 0 100 4 2 2 0 000-4zM2 5.5a3.5 3.5 0 115.898 2.549 5.507 5.507 0 013.034 4.084.75.75 0 11-1.482.235 4.001 4.001 0 00-7.9 0 .75.75 0 01-1.482-.236A5.507 5.507 0 013.102 8.05 3.49 3.49 0 012 5.5zM11 4a.75.75 0 100 1.5 1.5 1.5 0 01.666 2.844.75.75 0 00-.416.672v.352a.75.75 0 00.574.73c1.2.289 2.162 1.2 2.522 2.372a.75.75 0 101.434-.44 5.01 5.01 0 00-2.56-3.012A3 3 0 0011 4z"),
    ]

    row_svg = []
    for idx, (label, val, path_d) in enumerate(rows):
        y = 58 + idx * 25
        row_svg.append(
            f'<g transform="translate(25, {y})">'
            f'<svg x="0" y="-12" width="16" height="16" viewBox="0 0 16 16" fill="#f8d847">'
            f'<path fill-rule="evenodd" d="{path_d}"/></svg>'
            f'<text x="25" y="0" class="stat-label">{html.escape(label)}:</text>'
            f'<text x="215" y="0" class="stat-val">{html.escape(val)}</text>'
            f'</g>'
        )

    title = html.escape(f"{stats['login']}'s GitHub Stats")
    return f"""<svg width="450" height="195" viewBox="0 0 450 195" fill="none" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="statsTitle">
  <title id="statsTitle">{title}</title>
  <style>
    .header {{ font: 700 18px 'Segoe UI', Ubuntu, Sans-Serif; fill: #fe428e; }}
    .stat-label {{ font: 600 14px 'Segoe UI', Ubuntu, 'Helvetica Neue', Sans-Serif; fill: #a9fef7; }}
    .stat-val {{ font: 700 14px 'Segoe UI', Ubuntu, 'Helvetica Neue', Sans-Serif; fill: #a9fef7; }}
    .rank-text {{ font: 800 24px 'Segoe UI', Ubuntu, Sans-Serif; fill: #f8d847; }}
    .rank-sub {{ font: 600 10px 'Segoe UI', Ubuntu, Sans-Serif; fill: #a9fef7; letter-spacing: 0.6px; }}
  </style>
  <rect x="0.5" y="0.5" rx="10" width="449" height="194" fill="#141321" stroke="#e4e2e2" stroke-opacity="0.7"/>
  <text x="25" y="34" class="header">{title}</text>
  {''.join(row_svg)}
  <g transform="translate(365, 108)">
    <circle cx="0" cy="0" r="{r}" fill="none" stroke="#fe428e" stroke-opacity="0.2" stroke-width="6"/>
    <circle cx="0" cy="0" r="{r}" fill="none" stroke="#fe428e" stroke-width="6"
            stroke-linecap="round" stroke-dasharray="{circ:.2f}" stroke-dashoffset="{dash_offset:.2f}"
            transform="rotate(-90)"/>
    <text x="0" y="6" text-anchor="middle" class="rank-text">{rank}</text>
    <text x="0" y="56" text-anchor="middle" class="rank-sub">RANK</text>
  </g>
</svg>
"""


def render_langs_svg(stats: dict) -> str:
    langs = stats["languages"]
    sorted_langs = sorted(langs.items(), key=lambda kv: kv[1]["size"], reverse=True)[:8]
    total_size = sum(item[1]["size"] for item in sorted_langs) or 1

    bar_width = 350.0
    bar_x = 25.0
    bar_svg = []
    cur_x = bar_x
    for idx, (name, info) in enumerate(sorted_langs):
        w = (info["size"] / total_size) * bar_width
        if idx == len(sorted_langs) - 1:
            w = max(1.0, (bar_x + bar_width) - cur_x)
        bar_svg.append(
            f'<rect x="{cur_x:.2f}" y="0" width="{w:.2f}" height="8" fill="{html.escape(info["color"])}"/>'
        )
        cur_x += w

    items_svg = []
    for idx, (name, info) in enumerate(sorted_langs):
        col = idx % 2
        row = idx // 2
        x = 25 + col * 182
        y = 86 + row * 24
        pct = (info["size"] / total_size) * 100.0
        items_svg.append(
            f'<g transform="translate({x}, {y})">'
            f'<circle cx="5" cy="-4" r="5" fill="{html.escape(info["color"])}"/>'
            f'<text x="16" y="0" class="lang-name">{html.escape(name)} '
            f'<tspan class="lang-pct">{pct:.2f}%</tspan></text>'
            f'</g>'
        )

    return f"""<svg width="400" height="195" viewBox="0 0 400 195" fill="none" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="langsTitle">
  <title id="langsTitle">Most Used Languages</title>
  <style>
    .header {{ font: 700 18px 'Segoe UI', Ubuntu, Sans-Serif; fill: #fe428e; }}
    .lang-name {{ font: 600 12px 'Segoe UI', Ubuntu, Sans-Serif; fill: #a9fef7; }}
    .lang-pct {{ font: 400 12px 'Segoe UI', Ubuntu, Sans-Serif; fill: #f8d847; }}
  </style>
  <defs>
    <clipPath id="barClip">
      <rect x="25" y="0" width="350" height="8" rx="4"/>
    </clipPath>
  </defs>
  <rect x="0.5" y="0.5" rx="10" width="399" height="194" fill="#141321" stroke="#e4e2e2" stroke-opacity="0.7"/>
  <text x="25" y="34" class="header">Most Used Languages</text>
  <g transform="translate(0, 50)" clip-path="url(#barClip)">
    {''.join(bar_svg)}
  </g>
  {''.join(items_svg)}
</svg>
"""


def main() -> int:
    token = get_token()
    stats = fetch_stats(token, USERNAME)
    os.makedirs(OUT_DIR, exist_ok=True)
    stats_path = os.path.join(OUT_DIR, "github-stats.svg")
    langs_path = os.path.join(OUT_DIR, "top-langs.svg")
    with open(stats_path, "w", encoding="utf-8") as f:
        f.write(render_stats_svg(stats))
    with open(langs_path, "w", encoding="utf-8") as f:
        f.write(render_langs_svg(stats))
    print(f"Generated {stats_path} and {langs_path}: {json.dumps({k: v for k, v in stats.items() if k != 'languages'})}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
