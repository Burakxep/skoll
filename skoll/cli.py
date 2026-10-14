"""Command-line entry point.

  python -m skoll run --profile cybersec [--focus redteam] [--dry-run]
  python -m skoll list-profiles
  python -m skoll add-source --profile cybersec --subreddit redteamsec
  python -m skoll add-source --profile cybersec --feed https://example.com/rss
  python -m skoll check --profile cybersec
  python -m skoll weekly --profile cybersec [--no-fetch] [--end 2026-10-14]
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

import yaml

from .config import load_config, get_profile, list_profiles, DEFAULT_CONFIG, EXAMPLE_CONFIG
from .pipeline import run_profile
from .banner import print_banner
from . import __version__


def _cmd_run(args) -> int:
    config = load_config(args.config)
    profile = get_profile(config, args.profile)
    print_banner(f"profile: {args.profile}"
                 + (f" · focus: {args.focus}" if args.focus else ""))
    print(f"▶ Running profile '{args.profile}'"
          + (f" (focus={args.focus})" if args.focus else ""))
    result = run_profile(args.profile, profile, focus=args.focus,
                         dry_run=args.dry_run)
    c = result["counts"]
    print(f"\n✓ Done. raw={c['raw']} new={c['fresh']} kept={c['kept']}"
          + (f" (today's report: {c['report']})" if c.get("report", c["kept"]) != c["kept"] else ""))
    print("  Reports:")
    for kind, path in result["paths"].items():
        print(f"    {kind:7} {path}")
    if args.dry_run:
        print("\n  (dry run: history and latest.* were not touched)")
    else:
        print(f"\n  → Paste this into an AI Agent for analysis:")
        print(f"    reports/{args.profile}/latest.prompt.md")
    return 0


def _cmd_list(args) -> int:
    config = load_config(args.config)
    profs = list_profiles(config)
    print("Profiles:")
    for p in profs:
        srcs = ", ".join(config["profiles"][p].get("sources", []))
        print(f"  {p}  [{srcs}]")
    return 0


def _resolve_writable_config(args) -> Path:
    """add-source edits config.yaml; create it from the example if missing."""
    path = Path(args.config) if args.config else DEFAULT_CONFIG
    if not path.exists():
        if EXAMPLE_CONFIG.exists():
            path.write_text(EXAMPLE_CONFIG.read_text(encoding="utf-8"),
                            encoding="utf-8")
            print(f"  created {path} from example")
        else:
            print("  [!] no config to edit")
            sys.exit(1)
    return path


def _cmd_add_source(args) -> int:
    path = _resolve_writable_config(args)
    with open(path, encoding="utf-8") as fh:
        config = yaml.safe_load(fh) or {}
    profiles = config.setdefault("profiles", {})
    if args.profile not in profiles:
        print(f"  [!] profile '{args.profile}' not found"); return 1
    prof = profiles[args.profile]

    if args.subreddit:
        subs = prof.setdefault("reddit", {}).setdefault("subreddits", [])
        if args.subreddit not in subs:
            subs.append(args.subreddit)
            print(f"  + r/{args.subreddit}")
    if args.feed:
        feeds = prof.setdefault("rss", {}).setdefault("feeds", [])
        if args.feed not in feeds:
            feeds.append(args.feed)
            print(f"  + feed {args.feed}")
    if args.query:
        qs = prof.setdefault("github", {}).setdefault("queries", [])
        if args.query not in qs:
            qs.append(args.query)
            print(f"  + github query '{args.query}'")

    with open(path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(config, fh, sort_keys=False, allow_unicode=True)
    print(f"  saved {path}")
    return 0


def _cmd_check(args) -> int:
    """Quick connectivity/validity check of a profile's sources (dry run)."""
    config = load_config(args.config)
    profile = get_profile(config, args.profile)
    print(f"Checking profile '{args.profile}' (dry run, no history writes)...")
    run_profile(args.profile, profile, focus=args.focus, dry_run=True)
    return 0


def _cmd_weekly(args) -> int:
    from .weekly import collect
    from .weekly_report import write_weekly_reports

    config = load_config(args.config)
    profile = get_profile(config, args.profile)
    end = date.fromisoformat(args.end) if args.end else None
    print_banner(f"profile: {args.profile} · weekly")
    print(f"▶ Weekly trends for '{args.profile}'"
          + ("" if args.fetch else " (no fetch: recorded snapshots only)"))
    rep = collect(args.profile, profile, end=end, fetch=args.fetch)
    paths = write_weekly_reports(rep, args.profile)
    print(f"\n✓ {rep.week_id}: {rep.total.this} new relevant item(s) this week, "
          f"{rep.total.last} last week")
    print("  Reports:")
    for kind, path in paths.items():
        print(f"    {kind:7} {path}")
    print(f"\n  → Weekly analysis prompt:")
    print(f"    reports/{args.profile}/latest-weekly.prompt.md")
    return 0


HELP_EPILOG = """\
examples:
  python -m skoll run --profile cybersec                 daily scan + reports
  python -m skoll run --profile cybersec --focus recon   only items tagged recon
  python -m skoll check --profile cybersec               test sources, no history
  python -m skoll weekly --profile cybersec              this week vs last week
  python -m skoll add-source --profile cybersec --subreddit redteamsec

outputs:
  reports/<profile>/<date>/report.html      dashboard (filters, TR|EN, themes)
  reports/<profile>/<date>/digest.md        markdown digest
  reports/<profile>/<date>/prompt.md        analysis prompt for an LLM
  reports/<profile>/latest.prompt.md        prompt of the last real run
  reports/<profile>/weekly/<YYYY-Www>/      weekly trend report

No API key needed. Optional: export GITHUB_TOKEN=... to raise GitHub limits.
Run 'python -m skoll <command> -h' for the options of each command.
"""


def _parser() -> argparse.ArgumentParser:
    fmt = argparse.RawDescriptionHelpFormatter
    p = argparse.ArgumentParser(
        prog="skoll",
        description="Sköll: the wolf that chases the sun.\n"
                    "Daily, keyless discovery of new and rising security tools from "
                    "GitHub,\nHacker News, Reddit and research blogs, scored and "
                    "written to dated reports.",
        epilog=HELP_EPILOG, formatter_class=fmt)
    p.add_argument("-V", "--version", action="version",
                   version=f"skoll {__version__}")
    p.add_argument("--config", metavar="PATH",
                   help="config file (default: config.yaml, falls back to "
                        "config.example.yaml)")
    sub = p.add_subparsers(dest="cmd", title="commands", metavar="<command>")

    def profile_arg(sp):
        sp.add_argument("-p", "--profile", required=True, metavar="NAME",
                        help="profile from the config, e.g. cybersec "
                             "(see: list-profiles)")

    r = sub.add_parser(
        "run", help="scan all sources and write today's reports",
        formatter_class=fmt,
        description="Fetch every source of the profile, drop items reported on "
                    "earlier days,\nscore and filter the rest, and write today's "
                    "reports. Re-running the\nsame day adds new finds to the day's "
                    "report instead of replacing it.\nAlready-reported repos come "
                    "back as 'breakout' when their stars explode.",
        epilog="examples:\n"
               "  python -m skoll run --profile cybersec\n"
               "  python -m skoll run --profile cybersec --focus redteam\n"
               "  python -m skoll run --profile cybersec --dry-run")
    profile_arg(r)
    r.add_argument("-f", "--focus", metavar="TAG",
                   help="only report items with this focus tag "
                        "(e.g. redteam, recon, mobile)")
    r.add_argument("--dry-run", action="store_true",
                   help="preview: no dedup, no history writes; writes *.dry-run.* "
                        "files and leaves latest.* untouched")
    r.set_defaults(func=_cmd_run)

    c = sub.add_parser(
        "check", help="dry-run a profile to test its sources",
        formatter_class=fmt,
        description="Same as 'run --dry-run': fetch and score everything, write "
                    "*.dry-run.* reports,\nnever touch history or latest.*. Use it "
                    "after editing the config.")
    profile_arg(c)
    c.add_argument("-f", "--focus", metavar="TAG", help="only show items with this tag")
    c.set_defaults(func=_cmd_check)

    w = sub.add_parser(
        "weekly", help="trend report: this week vs last week",
        formatter_class=fmt,
        description="Compare the last 7 days with the 7 before: new relevant items "
                    "per source,\ncategory and keyword (by creation date), plus the "
                    "fastest-growing repos\nfrom daily snapshots. Writes "
                    "reports/<profile>/weekly/<YYYY-Www>/.",
        epilog="examples:\n"
               "  python -m skoll weekly --profile cybersec\n"
               "  python -m skoll weekly --profile cybersec --no-fetch\n"
               "  python -m skoll weekly --profile cybersec --end 2026-10-14")
    profile_arg(w)
    w.add_argument("--no-fetch", dest="fetch", action="store_false",
                   help="offline: use recorded daily snapshots only")
    w.add_argument("--end", metavar="YYYY-MM-DD",
                   help="last day of the week (default: today, UTC)")
    w.set_defaults(func=_cmd_weekly)

    a = sub.add_parser(
        "add-source", help="add a subreddit, RSS feed or GitHub query",
        formatter_class=fmt,
        description="Add sources to a profile without editing YAML by hand. "
                    "Creates config.yaml\nfrom config.example.yaml if it doesn't "
                    "exist yet. Duplicates are ignored.",
        epilog="examples:\n"
               "  python -m skoll add-source --profile cybersec --subreddit redteamsec\n"
               "  python -m skoll add-source --profile cybersec "
               "--feed https://example.com/feed.xml\n"
               "  python -m skoll add-source --profile cybersec "
               "--query \"kerberos OR adcs\"")
    profile_arg(a)
    a.add_argument("--subreddit", metavar="NAME", help="subreddit name, without r/")
    a.add_argument("--feed", metavar="URL", help="RSS/Atom feed URL")
    a.add_argument("--query", metavar="QUERY", help="GitHub search query")
    a.set_defaults(func=_cmd_add_source)

    l = sub.add_parser("list-profiles", help="list the profiles in the config",
                       description="List the profiles in the config and their sources.")
    l.set_defaults(func=_cmd_list)
    return p


def main(argv=None) -> int:
    p = _parser()
    args = p.parse_args(argv)
    if not args.cmd:            # bare 'python -m skoll': show help, not an error
        p.print_help()
        return 0
    if args.cmd == "add-source" and not (args.subreddit or args.feed or args.query):
        p.parse_args(["add-source", "-h"])  # nothing to add: show its help
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
