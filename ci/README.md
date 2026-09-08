# GitHub Actions workflows — move these into place

Remote tooling cannot write to `.github/` (workflows and dependabot) (protected path). From your terminal:

    mkdir -p .github/workflows && git mv ci/ci.yml ci/weekly.yml .github/workflows/ && git mv ci/dependabot.yml .github/dependabot.yml && rmdir ci 2>/dev/null; git commit -am "ci: workflows in place"

Then in the GitHub repo settings set Pages → Source → "GitHub Actions". The weekly job runs Mondays 14:00 UTC
and can be triggered manually from the Actions tab (workflow_dispatch).
