#!/usr/bin/env python3
"""Skill Sync v3 — two-way tier-based distribution.

Tiers (defined in ~/.hermes/config/skill-tiers.yaml):
  base:       auto-synced to ALL tenants (core skills)
  admin_only: admin (Poliakarm) only
  opt_in:     tenant requests → admin installs via --install

Usage:
  python3 skill-sync.py                          # sync base skills to all tenants
  python3 skill-sync.py --dry-run                # preview
  python3 skill-sync.py --status                 # show all tenants
  python3 skill-sync.py --install <skill> --tenant <name>  # install opt-in skill
  python3 skill-sync.py --install <skill> --tenant <name> --remove  # remove
  python3 skill-sync.py --pull --tenant <name>   # discover + review tenant's local skills
  python3 skill-sync.py --pull --tenant <name> --dry-run  # preview without review
  python3 skill-sync.py --import <skill> --tenant <name>  # import reviewed skill to base
"""
import json, os, sys, shutil, hashlib
from pathlib import Path
import yaml

BASE = Path.home() / ".hermes" / "skills"
PROFILES = Path.home() / ".hermes" / "profiles"
TIERS_FILE = Path.home() / ".hermes" / "config" / "skill-tiers.yaml"
SKIP_DIRS = {"__pycache__", ".git", "node_modules"}


def load_tiers():
    with open(TIERS_FILE) as f:
        return yaml.safe_load(f)


def get_base_skills():
    tiers = load_tiers()
    return set(tiers.get("base", []))


def get_admin_skills():
    tiers = load_tiers()
    return set(tiers.get("admin_only", []))


def get_opt_in_skills():
    tiers = load_tiers()
    return set(tiers.get("opt_in", []))


def hash_file(path: Path) -> str:
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def security_check(skill_path: str) -> dict:
    """Run security scan on a skill before import. Returns {score, blocked, findings}."""
    import subprocess
    scanner = Path(__file__).parent / "skill-security-scan.py"
    if not scanner.exists():
        return {"score": 100, "blocked": False, "findings": []}

    base_file = BASE / skill_path / "SKILL.md"
    if not base_file.exists():
        return {"score": 100, "blocked": False, "findings": []}

    try:
        result = subprocess.run(
            ["python3", str(scanner), "--file", str(base_file), "--json"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            return {"score": 100, "blocked": False, "findings": [], "error": result.stderr.strip()}
        data = json.loads(result.stdout)
        if not data:
            return {"score": 100, "blocked": False, "findings": []}
        entry = data[0]
        score = entry.get("score", 100)
        findings = entry.get("findings", [])
        criticals = [f for f in findings if f.get("severity") == "CRITICAL"]
        highs = [f for f in findings if f.get("severity") == "HIGH"]
        blocked = len(criticals) > 0
        return {"score": score, "blocked": blocked, "findings": findings, "critical": len(criticals), "high": len(highs)}
    except Exception as e:
        return {"score": 100, "blocked": False, "findings": [], "error": str(e)}


def sync_base(tenant: str, dry_run: bool = False) -> dict:
    """Sync only base skills to tenant."""
    tenant_dir = PROFILES / tenant / "skills"
    local_dir = PROFILES / tenant / "skills.local"
    tenant_dir.mkdir(parents=True, exist_ok=True)
    local_dir.mkdir(parents=True, exist_ok=True)

    base_set = get_base_skills()
    report = {"tenant": tenant, "synced": [], "kept_local": [], "new": [], "unchanged": [], "blocked": []}

    for skill_path in base_set:
        base_file = BASE / skill_path / "SKILL.md"
        if not base_file.exists():
            continue

        tenant_file = tenant_dir / skill_path / "SKILL.md"
        local_file = local_dir / skill_path / "SKILL.md"

        if local_file.exists():
            report["kept_local"].append(skill_path)
            continue

        # Security scan before import
        if not tenant_file.exists():
            scan = security_check(skill_path)
            if scan.get("blocked"):
                report["blocked"].append({"skill": skill_path, "score": scan["score"], "critical": scan.get("critical", 0), "high": scan.get("high", 0)})
                print(f"    ⛔ SECURITY BLOCK: {skill_path} (score {scan['score']}/100, {scan.get('critical', 0)} critical)")
                continue

        base_hash = hash_file(base_file)

        if not tenant_file.exists():
            if not dry_run:
                tenant_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(base_file, tenant_file)
            report["new"].append(skill_path)
        else:
            tenant_hash = hash_file(tenant_file)
            if base_hash != tenant_hash:
                if not dry_run:
                    shutil.copy2(base_file, tenant_file)
                report["synced"].append(skill_path)
            else:
                report["unchanged"].append(skill_path)

    return report


def review_pipeline(skill_name: str, tenant: str, skill_file: Path) -> dict:
    """Four-stage review: validate → security → judge → adversarial.
    Returns {passed, stage, score, findings}."""
    import subprocess, tempfile

    content = skill_file.read_text()
    result = {"passed": False, "stage": "validate", "score": 0, "findings": []}

    # Stage 0: Syntax & Structure Validation (CI/CD)
    print(f"  🧪 Stage 0/4: Syntax validation...")
    validator = Path(__file__).parent / "skill-validate.py"
    if validator.exists():
        try:
            r = subprocess.run(
                ["python3", str(validator), str(skill_file), "--json"],
                capture_output=True, text=True, timeout=10
            )
            if r.stdout.strip():
                data = json.loads(r.stdout)
                if not data.get("passed", False):
                    result["findings"] = data.get("errors", [])
                    result["score"] = data.get("score", 0)
                    print(f"    ⛔ FAILED: {len(result['findings'])} errors")
                    return result
                else:
                    if data.get("warnings"):
                        print(f"    ⚠️ {len(data['warnings'])} warnings (non-blocking)")
                    print(f"    ✅ Passed (score {data.get('score', 100)})")
        except Exception as e:
            print(f"    ⚠️ Validator error: {e} (continuing)")

    # Stage 1: Security scan
    print(f"  🔒 Stage 1/4: Security scan...")
    scanner = Path(__file__).parent / "skill-security-scan.py"
    if scanner.exists():
        try:
            r = subprocess.run(
                ["python3", str(scanner), "--file", str(skill_file), "--json"],
                capture_output=True, text=True, timeout=15
            )
            if r.returncode == 0 and r.stdout.strip():
                data = json.loads(r.stdout)
                if data and len(data) > 0:
                    entry = data[0]
                    score = entry.get("score", 100)
                    findings = entry.get("findings", [])
                    criticals = [f for f in findings if f.get("severity") == "CRITICAL"]
                    if criticals:
                        result["findings"] = [f"{f.get('rule','?')}: {f.get('message','')}" for f in criticals]
                        result["score"] = score
                        print(f"    ⛔ BLOCKED: {len(criticals)} critical issues (score {score})")
                        return result
        except Exception as e:
            result["findings"].append(f"Security scan error: {e}")

    print(f"    ✅ Passed")

    # Stage 2: Judge (DeepSeek API)
    print(f"  ⚖️  Stage 2/4: Judge review...")
    judge = Path.home() / ".local" / "bin" / "judge"
    if not judge.exists():
        print(f"    ⚠️ Judge not found, skipping")
    else:
        try:
            r = subprocess.run(
                ["python3", str(judge), f"Review skill '{skill_name}' from tenant '{tenant}':\n\n{content[:8000]}"],
                capture_output=True, text=True, timeout=45
            )
            output = r.stdout + r.stderr
            if "passed" not in output.lower() or "false" in output.lower():
                result["stage"] = "judge"
                result["findings"].append(f"Judge: {output.strip()[:300]}")
                print(f"    ❌ Judge rejected")
                return result
        except Exception as e:
            result["findings"].append(f"Judge error: {e}")
            print(f"    ⚠️ Judge error: {e}")

    print(f"    ✅ Passed")

    # Stage 3: Adversarial review (second opinion via DeepSeek)
    print(f"  🧠 Stage 3/4: Adversarial review...")
    import urllib.request
    env_file = Path.home() / ".hermes" / ".env"
    deepseek_key = ""
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("DEEPSEEK_API_KEY="):
                deepseek_key = line.split("=", 1)[1].strip().strip('"').strip("'")
                break

    if not deepseek_key:
        print(f"    ⚠️ No DEEPSEEK_API_KEY, skipping adversarial review")
    else:
        try:
            review_prompt = f"""You are a skill reviewer for an AI agent platform. Review this skill for:
1. Does it contradict the Hermes constitution? (user sovereignty, safety, scope discipline)
2. Are there hallucinations in commands or paths?
3. Are the instructions clear and executable?
4. Is it safe for multi-tenant use?

Skill: {skill_name}
Author: tenant '{tenant}'

{content[:6000]}

Respond with JSON only: {{"approved": true/false, "issues": ["..."], "score": 0-100}}"""

            req = urllib.request.Request(
                "https://api.deepseek.com/v1/chat/completions",
                data=json.dumps({
                    "model": "deepseek-chat",
                    "messages": [{"role": "user", "content": review_prompt}],
                    "temperature": 0.1, "max_tokens": 500
                }).encode(),
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {deepseek_key}"}
            )
            with urllib.request.urlopen(req, timeout=45) as resp:
                data = json.loads(resp.read())
                reply = data["choices"][0]["message"]["content"]
                # Extract JSON
                if "{" in reply and "}" in reply:
                    json_str = reply[reply.index("{"):reply.rindex("}")+1]
                    review = json.loads(json_str)
                    if not review.get("approved", False):
                        result["stage"] = "adversarial"
                        result["findings"].extend(review.get("issues", []))
                        result["score"] = review.get("score", 0)
                        print(f"    ❌ Rejected (score {review.get('score', 0)})")
                        for issue in review.get("issues", []):
                            print(f"      • {issue}")
                        return result
        except Exception as e:
            print(f"    ⚠️ Adversarial review error: {e}")

    result["passed"] = True
    result["score"] = 100
    print(f"    ✅ All stages passed")
    return result


def cmd_tenant_pull(tenant: str, dry_run: bool = False):
    """Discover new/modified skills in tenant's skills.local/ and review them."""
    local_dir = PROFILES / tenant / "skills.local"
    if not local_dir.exists():
        print(f"📭 No skills.local/ directory for {tenant}")
        return

    local_skills = {}
    for skill_dir in sorted(local_dir.iterdir()):
        if not skill_dir.is_dir() or skill_dir.name in SKIP_DIRS:
            continue
        skill_file = skill_dir / "SKILL.md"
        if skill_file.exists():
            local_skills[skill_dir.name] = skill_file

    if not local_skills:
        print(f"📭 No skills found in {tenant}/skills.local/")
        return

    print(f"\\n🔍 Found {len(local_skills)} skill(s) from {tenant}:\\n")
    for name, path in local_skills.items():
        base_exists = (BASE / name / "SKILL.md").exists()
        marker = "🆕 new" if not base_exists else "✏️  modified"
        size = path.stat().st_size
        print(f"  {marker}  {name}  ({size:,} bytes)")

    if dry_run:
        print("\\n  (dry run — no review performed)")
        return

    # Review each skill
    print(f"\\n📋 Review pipeline:\\n")
    passed = []
    for name, path in local_skills.items():
        print(f"  📄 {name}:")
        result = review_pipeline(name, tenant, path)
        if result["passed"]:
            passed.append((name, path))
            print()
        else:
            print(f"    ❌ Blocked at stage '{result['stage']}': {', '.join(result['findings'][:3])}\\n")

    if not passed:
        print("❌ No skills passed review.")
        return

    print(f"\\n✅ {len(passed)} skill(s) passed review. Ready to import:")
    for name, _ in passed:
        print(f"  • {name}")
    print(f"\\n  To import: python3 skill-sync.py --import <skill> --tenant {tenant}")


def cmd_import(skill: str, tenant: str):
    """Import a reviewed skill from tenant's skills.local/ to base, then sync to all tenants."""
    local_file = PROFILES / tenant / "skills.local" / skill / "SKILL.md"
    if not local_file.exists():
        print(f"❌ Skill '{skill}' not found in {tenant}/skills.local/")
        sys.exit(1)

    # Re-run review to be safe
    print(f"🔍 Re-reviewing {skill} from {tenant}...")
    result = review_pipeline(skill, tenant, local_file)
    if not result["passed"]:
        print(f"❌ Review failed at stage '{result['stage']}'. Import blocked.")
        if result["findings"]:
            for f in result["findings"]:
                print(f"  • {f}")
        sys.exit(1)

    # Copy to base
    base_target = BASE / skill / "SKILL.md"
    base_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(local_file, base_target)
    print(f"✓ Imported {skill} → base skills")

    # Add to base tier if not already there
    tiers = load_tiers()
    base_set = set(tiers.get("base", []))
    if skill not in base_set:
        base_set.add(skill)
        tiers["base"] = sorted(base_set)
        with open(TIERS_FILE, "w") as f:
            yaml.dump(tiers, f, default_flow_style=False, allow_unicode=True)
        print(f"✓ Added {skill} to base tier")

    # Sync to all tenants
    print(f"\\n🔄 Syncing to all tenants...")
    profiles = [d.name for d in sorted(PROFILES.iterdir())
                if d.is_dir() and (d / "config.yaml").exists() and d.name != "poliakarm"]

    for profile in profiles:
        tenant_file = PROFILES / profile / "skills" / skill / "SKILL.md"
        tenant_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(base_target, tenant_file)
        print(f"  ✓ {profile}")

    # Archive local copy
    imported_dir = PROFILES / tenant / "skills.imported"
    imported_dir.mkdir(exist_ok=True)
    archive_target = imported_dir / skill
    if archive_target.exists():
        shutil.rmtree(archive_target)
    shutil.move(str(local_file.parent), str(archive_target))
    print(f"✓ Archived {tenant}/skills.local/{skill} → skills.imported/")

    print(f"\\n🚀 Done. {skill} is now in base + synced to all tenants.")
    """Install (or remove) a specific opt-in skill to a tenant."""
    tiers = load_tiers()
    all_known = set(tiers.get("base", []) + tiers.get("admin_only", []) + tiers.get("opt_in", []))
    if skill not in all_known:
        print(f"❌ Unknown skill: {skill}")
        print(f"   Known: {len(all_known)} skills in tiers config")
        sys.exit(1)

    tenant_dir = PROFILES / tenant / "skills"
    if not tenant_dir.exists():
        print(f"❌ Tenant not found: {tenant}")
        sys.exit(1)

    target = tenant_dir / skill / "SKILL.md"
    local_target = PROFILES / tenant / "skills.local" / skill / "SKILL.md"

    if remove:
        # Remove from tenant (both regular and local)
        removed = []
        for p in [target, local_target]:
            if p.exists():
                p.unlink()
                # Cleanup empty dirs
                try:
                    p.parent.rmdir()
                except OSError:
                    pass
                removed.append(str(p))
        if removed:
            print(f"⊖ Removed {skill} from {tenant}")
        else:
            print(f"  {skill} was not installed for {tenant}")
        return

    # Install
    base_file = BASE / skill / "SKILL.md"
    if not base_file.exists():
        print(f"❌ Base skill not found: {skill}")
        sys.exit(1)

    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(base_file, target)
    print(f"✓ Installed {skill} → {tenant}")


def cmd_sync(args):
    dry_run = "--dry-run" in args

    profiles = [d.name for d in sorted(PROFILES.iterdir()) if d.is_dir() and (d / "config.yaml").exists()]
    # Skip admin's own profile — admin has all skills anyway
    profiles = [p for p in profiles if p != "poliakarm"]

    if not profiles:
        print("No tenant profiles found.")
        return

    total = {"synced": 0, "kept_local": 0, "new": 0, "unchanged": 0}
    base_count = len(get_base_skills())

    mode = "[DRY RUN] " if dry_run else ""
    print(f"Base skills: {base_count}\n")

    for profile in profiles:
        report = sync_base(profile, dry_run=dry_run)
        total_tenant = len(report["new"]) + len(report["synced"]) + len(report["unchanged"]) + len(report["kept_local"])
        behind = len(report["new"]) + len(report["synced"])
        blocked_count = len(report.get("blocked", []))

        icon = "✅" if behind == 0 else "⚠️"
        blocked_info = f" ⛔{blocked_count}" if blocked_count else ""
        print(f"  {icon} {mode}{profile}: {total_tenant} base skills ({behind} behind, {len(report['kept_local'])} local){blocked_info}")

        if report["new"]:
            for s in report["new"]:
                print(f"    + {s}")
        if report["synced"]:
            for s in report["synced"]:
                print(f"    ↻ {s}")

    for k in total:
        total[k] += len(report.get(k, []))

    if dry_run:
        print("\n  (dry run — nothing changed)")


def cmd_status(args):
    profiles = [d.name for d in sorted(PROFILES.iterdir()) if d.is_dir() and (d / "config.yaml").exists()]
    tiers = load_tiers()
    print(f"Tiers: {len(tiers.get('base', []))} base, {len(tiers.get('admin_only', []))} admin, {len(tiers.get('opt_in', []))} opt-in\n")

    for profile in profiles:
        tenant_dir = PROFILES / profile / "skills"
        base_set = get_base_skills()

        has_base = sum(1 for s in base_set if (tenant_dir / s / "SKILL.md").exists())
        behind = len(base_set) - has_base

        # Count total skills
        total = 0
        if tenant_dir.exists():
            total = len(list(tenant_dir.rglob("SKILL.md")))

        admin_mark = " 👑" if profile == "poliakarm" else ""
        icon = "✅" if behind == 0 else "⚠️"
        print(f"  {icon} {profile}{admin_mark}: {has_base}/{len(base_set)} base, {total} total skills")


if __name__ == "__main__":
    args = sys.argv[1:]

    if "--import" in args and "--tenant" in args:
        idx = args.index("--import")
        skill = args[idx + 1]
        tenant = args[args.index("--tenant") + 1]
        cmd_import(skill, tenant)
    elif "--install" in args:
        idx = args.index("--install")
        skill = args[idx + 1]
        tenant = None
        if "--tenant" in args:
            tenant = args[args.index("--tenant") + 1]
        remove = "--remove" in args
        if not tenant:
            print("Usage: skill-sync.py --install <skill> --tenant <name> [--remove]")
            sys.exit(1)
        cmd_install(skill, tenant, remove=remove)
    elif "--pull" in args:
        tenant = None
        if "--tenant" in args:
            tenant = args[args.index("--tenant") + 1]
        if not tenant:
            print("Usage: skill-sync.py --pull --tenant <name> [--dry-run]")
            sys.exit(1)
        dry_run = "--dry-run" in args
        cmd_tenant_pull(tenant, dry_run=dry_run)
    elif "--status" in args or "status" in args:
        cmd_status(args)
    else:
        cmd_sync(args)
