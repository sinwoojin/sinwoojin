from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path
from typing import Any


USERNAME = os.environ.get("PROFILE_USERNAME", "sinwoojin")
README_PATH = Path(os.environ.get("README_PATH", "README.md"))
LANGUAGE_SVG_PATH = Path(os.environ.get("LANGUAGE_SVG_PATH", "assets/language-share.svg"))
START_MARKER = "<!-- AUTO-STATS:START -->"
END_MARKER = "<!-- AUTO-STATS:END -->"
KST = timezone(timedelta(hours=9))
LANGUAGE_COLORS = {
    "TypeScript": "#3178c6",
    "JavaScript": "#f1e05a",
    "CSS": "#663399",
    "HTML": "#e34c26",
    "Go": "#00add8",
    "Shell": "#89e051",
    "Java": "#b07219",
    "C": "#555555",
    "Dockerfile": "#384d54",
}


def github_get(url: str) -> Any:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "profile-readme-updater",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_repositories() -> list[dict[str, Any]]:
    repos: list[dict[str, Any]] = []
    page = 1
    while True:
        url = (
            f"https://api.github.com/users/{USERNAME}/repos"
            f"?per_page=100&page={page}&sort=updated&type=owner"
        )
        batch = github_get(url)
        if not batch:
            break
        repos.extend(repo for repo in batch if not repo.get("fork"))
        page += 1
    return repos


def fetch_language_totals(repos: list[dict[str, Any]]) -> dict[str, int]:
    totals: dict[str, int] = {}
    for repo in repos:
        languages_url = repo.get("languages_url")
        if not isinstance(languages_url, str) or not languages_url:
            continue
        try:
            languages = github_get(languages_url)
        except urllib.error.HTTPError as error:
            print(f"warning: failed to fetch languages for {repo.get('name')}: {error}", file=sys.stderr)
            continue
        if not isinstance(languages, dict):
            continue
        for language, byte_count in languages.items():
            if isinstance(language, str) and isinstance(byte_count, int):
                totals[language] = totals.get(language, 0) + byte_count
    return totals


def render_language_svg(language_totals: dict[str, int]) -> str:
    total_bytes = sum(language_totals.values())
    width = 520
    legend_columns = 3
    legend_item_width = 156
    legend_row_height = 26
    legend_top = 70
    bottom_padding = 22
    max_languages = 8
    languages = sorted(language_totals.items(), key=lambda item: item[1], reverse=True)[:max_languages]
    legend_rows = (len(languages) + legend_columns - 1) // legend_columns
    height = legend_top + legend_rows * legend_row_height + bottom_padding

    if total_bytes == 0:
        languages = [("No language data", 1)]
        total_bytes = 1
        legend_rows = 1
        height = legend_top + legend_rows * legend_row_height + bottom_padding

    bar_x = 24
    bar_y = 40
    bar_width = width - 48
    current_x = bar_x
    segments: list[str] = []
    rows: list[str] = []

    for index, (language, byte_count) in enumerate(languages):
        percent = byte_count / total_bytes * 100
        color = LANGUAGE_COLORS.get(language, "#8b949e")
        segment_width = bar_width * byte_count / total_bytes
        if index == len(languages) - 1:
            segment_width = bar_x + bar_width - current_x
        segments.append(
            f'<rect x="{current_x:.2f}" y="{bar_y}" width="{segment_width:.2f}" height="10" fill="{color}" />'
        )
        current_x += segment_width

        column = index % legend_columns
        row = index // legend_columns
        item_x = 24 + column * legend_item_width
        item_y = legend_top + row * legend_row_height
        rows.append(
            f'<circle cx="{item_x + 6}" cy="{item_y}" r="5" fill="{color}" />'
            f'<text x="{item_x + 18}" y="{item_y + 4}">'
            f'<tspan class="label">{escape(language)}</tspan>'
            f'<tspan class="percent"> {percent:.1f}%</tspan>'
            f'</text>'
        )

    return f'''<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" fill="none" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="title desc">
  <title id="title">Public repository language share</title>
  <desc id="desc">Generated daily from GitHub public repository language data.</desc>
  <style>
    .title {{ fill: #24292f; font: 600 16px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    .caption {{ fill: #57606a; font: 12px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    .label {{ fill: #24292f; font: 13px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    .percent {{ fill: #57606a; font: 12px ui-monospace, SFMono-Regular, Consolas, monospace; }}
    @media (prefers-color-scheme: dark) {{
      .title, .label {{ fill: #f0f6fc; }}
      .caption, .percent {{ fill: #8b949e; }}
    }}
  </style>
  <text x="24" y="24" class="title">Language Share</text>
  <text x="496" y="24" class="caption" text-anchor="end">public repos</text>
  <clipPath id="bar"><rect x="{bar_x}" y="{bar_y}" width="{bar_width}" height="10" rx="5" /></clipPath>
  <g clip-path="url(#bar)">
    {''.join(segments)}
  </g>
  {''.join(rows)}
</svg>
'''


def write_language_svg(language_totals: dict[str, int]) -> None:
    if not language_totals and LANGUAGE_SVG_PATH.exists():
        print("warning: language API returned no data; keeping existing SVG", file=sys.stderr)
        return

    LANGUAGE_SVG_PATH.parent.mkdir(parents=True, exist_ok=True)
    LANGUAGE_SVG_PATH.write_text(render_language_svg(language_totals), encoding="utf-8")


def render_recent_repos(repos: list[dict[str, Any]]) -> str:
    visible_repos = sorted(
        repos,
        key=lambda repo: repo.get("pushed_at") or repo.get("updated_at") or "",
        reverse=True,
    )[:5]
    if not visible_repos:
        return "No public repositories found yet."

    lines: list[str] = []
    for repo in visible_repos:
        name = repo["name"]
        url = repo["html_url"]
        description = repo.get("description") or "No description yet"
        language = repo.get("language") or "Mixed"
        stars = repo.get("stargazers_count", 0)
        lines.append(f"- [{name}]({url}) · {language} · ⭐ {stars} — {description}")
    return "\n".join(lines)


def render_stats(repos: list[dict[str, Any]]) -> str:
    updated_at = datetime.now(KST).strftime("%Y-%m-%d %H:%M KST")
    public_repo_count = len(repos)
    total_stars = sum(int(repo.get("stargazers_count", 0)) for repo in repos)

    return f"""<!-- AUTO-STATS:START -->
_Last updated: {updated_at} · public repos: {public_repo_count} · total stars: {total_stars}_

### 🧭 Recently Updated Public Repos

{render_recent_repos(repos)}
<!-- AUTO-STATS:END -->"""


def update_readme(stats_block: str) -> None:
    readme = README_PATH.read_text(encoding="utf-8")
    if START_MARKER not in readme or END_MARKER not in readme:
        readme = readme.rstrip() + "\n\n" + START_MARKER + "\n" + END_MARKER + "\n"

    before, rest = readme.split(START_MARKER, 1)
    _, after = rest.split(END_MARKER, 1)
    README_PATH.write_text(before + stats_block + after, encoding="utf-8")


def main() -> int:
    repos = fetch_repositories()
    write_language_svg(fetch_language_totals(repos))
    update_readme(render_stats(repos))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
