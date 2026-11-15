#!/usr/bin/env python3
"""PR24: somente leitura, valida o stack e o SHA antes de janela de release.

Uso: GITHUB_TOKEN=<segredo> python scripts/homolog_merge_preflight.py
Nenhum comando de merge/deploy é emitido por este script.
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

REPO = "Brunohvg/vidalys-fideliza"
EXPECTED_HOMOLOG = "c25d668ec1b668c3a254b816cc96b6236a0dadb2"
STACK = (
    (18, "refactor/omnichannel-customer-identity",
     "homolog", "0853282be9cef0169b4d66cf7c4dd1b974c30d53"),
    (19, "feature/pr19-channel-order-ingestion",
     "refactor/omnichannel-customer-identity",
     "9d72304a6696439db679ca630577b21e49bc595e"),
    (20, "feature/pr20-loyalty-offline-engine",
     "feature/pr19-channel-order-ingestion",
     "c7f7f9fa7cef269e614933c1e46ca1be33509647"),
    (21, "feature/pr21-frontend-routes-visual-qa",
     "feature/pr20-loyalty-offline-engine",
     "fbfa046a12c22acc8acc11d288b8e4c4b2f45950"),
    (22, "feature/pr22-consolidation-homolog-gates",
     "feature/pr21-frontend-routes-visual-qa",
     "d02d6a64feca0ed87b8039c3697011f8bd7646ab"),
    (23, "feature/pr23-compliance-conformance-fixes",
     "feature/pr22-consolidation-homolog-gates",
     "2aa3168ca40b361a8095c2345a2c6aae0ebacb3b"),
)


def get(path):
    token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
    request = urllib.request.Request(
        "https://api.github.com/repos/" + REPO + "/" + path,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "vidalys-pr24-release-preflight",
            **({"Authorization": "Bearer " + token} if token else {}),
        },
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.load(response)


def validate(prs, actual_homolog, successful_heads, ancestry):
    """Checagens puras; retornam falhas claras sem dados privados."""
    issues = []
    if actual_homolog != EXPECTED_HOMOLOG:
        issues.append("homolog mudou: refaça revisão de diffs e atualize o SHA aprovado")
    for number, head, base, sha in STACK:
        pr = prs[number]
        if pr.get("state") != "open" or pr.get("merged"):
            issues.append(f"#{number} já mudou de estado; pare e revise a sequência")
        if pr.get("draft"):
            issues.append(f"#{number} continua draft: falta revisão e Ready for review")
        if pr.get("head", {}).get("ref") != head or pr.get("base", {}).get("ref") != base:
            issues.append(f"#{number} base/head diferentes da cadeia aprovada")
        if pr.get("head", {}).get("sha") != sha:
            issues.append(f"#{number} SHA mudou; refaça CI e revisão de segurança")
        if pr.get("mergeable") is False:
            issues.append(f"#{number} conflitos de merge")
        if sha not in successful_heads:
            issues.append(f"#{number} não tem workflow SUCCESS concluído no SHA aprovado")
        if ancestry.get((base, head)) is not True:
            issues.append(f"#{number} não é descendente linear da base")
    return issues


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--self-test":
        sample = {n: {
            "state": "open", "merged": False, "draft": False, "mergeable": True,
            "head": {"ref": h, "sha": s}, "base": {"ref": b},
        } for n, h, b, s in STACK}
        ancestry = {(b, h): True for _, h, b, _ in STACK}
        heads = {s for _, _, _, s in STACK}
        assert validate(sample, EXPECTED_HOMOLOG, heads, ancestry) == []
        sample[19]["draft"] = True
        assert any("#19 continua draft" in issue
                   for issue in validate(sample, EXPECTED_HOMOLOG, heads, ancestry))
        print("SELF_TEST_OK")
        return 0

    try:
        branch = get("branches/homolog")
        actual = branch["commit"]["sha"]
        prs = {n: get(f"pulls/{n}") for n, *_ in STACK}
        runs = get("actions/runs?per_page=100")["workflow_runs"]
        success = {
            run.get("head_sha") for run in runs
            if run.get("status") == "completed" and run.get("conclusion") == "success"
        }
        ancestry = {}
        for _, head, base, _ in STACK:
            b = urllib.parse.quote(base, safe="")
            h = urllib.parse.quote(head, safe="")
            diff = get(f"compare/{b}...{h}")
            ancestry[(base, head)] = (
                diff.get("behind_by") == 0
                and diff.get("ahead_by", 0) > 0
                and diff.get("status") in {"ahead", "identical"}
            )
    except (urllib.error.URLError, KeyError, ValueError, TimeoutError) as exc:
        print(f"BLOCK: API GitHub inacessível ou resposta incompleta ({type(exc).__name__}).")
        return 2

    issues = validate(prs, actual, success, ancestry)
    for n, _, base, sha in STACK:
        print(f"PR#{n}: base={base} head={sha[:12]} "
              f"draft={prs[n].get('draft')} ci={'OK' if sha in success else 'NAO_VERIFICADO'}")
    for issue in issues:
        print("BLOCK: " + issue)
    if issues:
        print("MERGE_GATE=BLOCKED")
        return 2
    print("MERGE_PREFLIGHT_OK; backup/restore, aprovação e auto-deploy OFF são gates separados.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
