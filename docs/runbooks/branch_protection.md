# Runbook: GitHub Branch Protection Configuration

**Document Path:** `docs/runbooks/branch_protection.md`  
**Target Branches:** `main`, `main-clean`  
**Audience:** Repository Administrators & DevOps Engineers  
**Enforcement Standard:** Zero unreviewed code, zero failed CI checks, linear history, strict CODEOWNERS sign-off.

---

## 1. Objective

This runbook specifies the exact procedure for configuring GitHub Branch Protection rules (and GitHub Repository Rulesets) for the Disha AI repository. Once enabled, direct pushes to `main` and `main-clean` are blocked; all changes must pass through pull requests validated by our 8-stage automated CI matrix and approved by designated domain code owners.

---

## 2. GitHub Web UI Click-Path (Classic Branch Protection)

Follow these exact navigation steps in the GitHub web interface:

### Step 1: Open Branch Protection Settings
1. Navigate to the repository root: `https://github.com/<owner>/<repo>`
2. Click the **Settings** tab (gear icon in the top repository navigation bar).
3. In the left sidebar under the **Code and automation** section, click **Branches**.
4. Under **Branch protection rules**, click the **Add branch protection rule** button (or click **Edit** next to `main`).

---

### Step 2: Configure Branch Pattern
- In the **Branch name pattern** field, input:
  ```text
  main
  ```
  *(Repeat this setup for `main-clean` or use the pattern `main*`)*

---

### Step 3: Enforce Pull Request Discipline
1. Check :white_check_mark: **Require a pull request before merging**
   - **Required approvals**: Select `1` (or `2` for production multi-reviewer compliance).
   - Check :white_check_mark: **Dismiss stale pull request approvals when new commits are pushed**  
     *(Invalidates previous approvals if code changes before merge)*
   - Check :white_check_mark: **Require review from Code Owners**  
     *(Mandates sign-off from domain leads specified in `.github/CODEOWNERS`)*
   - Check :white_check_mark: **Restrict who can dismiss pull request reviews**

---

### Step 4: Enforce Automated CI Status Checks
1. Check :white_check_mark: **Require status checks to pass before merging**
2. Check :white_check_mark: **Require branches to be up to date before merging**  
   *(Ensures code has been tested against latest target HEAD)*
3. In the search box **Status checks that are required**, search and select each of the 8 canonical CI job names defined in `.github/workflows/ci.yml`:
   - `Secrets & Gitleaks Audit`
   - `Container & Dependency Vulnerability Scan (Trivy)`
   - `Code Quality & Ruff Linter`
   - `Static Type Check (Pyright)`
   - `Hardcode & Secret Hygiene Check`
   - `Living Documentation Drift Audit`
   - `Architecture Diagram Verification`
   - `Canonical Test Matrix (Pytest)`

---

### Step 5: Enforce History & Integrity Restrictions
1. Check :white_check_mark: **Require conversation resolution before merging**  
   *(All PR review comments must be explicitly marked resolved)*
2. Check :white_check_mark: **Require signed commits** *(Recommended for clinical audit compliance)*
3. Check :white_check_mark: **Require linear history**  
   *(Blocks non-fast-forward merge commits; enforces clean rebase/squash commits)*
4. Check :white_check_mark: **Do not allow bypassing the above settings**  
   *(Prevents repository administrators from pushing unverified commits or bypassing CI)*
5. Confirm that **Allow force pushes** is **UNCHECKED** (:x: *Never allow force pushing to protected branches*).
6. Confirm that **Allow deletions** is **UNCHECKED** (:x: *Never allow branch deletion*).

---

### Step 6: Save Configuration
1. Scroll to the bottom of the page.
2. Click **Create** (or **Save changes**).
3. If prompted, confirm with your GitHub 2FA / password.

---

## 3. Modern GitHub Rulesets Alternative (Recommended)

GitHub Repository Rulesets provide declarative branch governance with inheritance.

### Click-Path:
1. Go to **Settings** > **Rules** > **Rulesets**.
2. Click **New ruleset** > **New branch ruleset**.
3. Configure:
   - **Ruleset Name**: `Production Protection Invariants`
   - **Enforcement status**: `Active`
   - **Target branches**: Select **Add target** > **Include default branch** and **Include by pattern** (`main-clean`).
4. Under **Branch rules**:
   - Check **Restrict deletions**
   - Check **Block force pushes**
   - Check **Require linear history**
   - Check **Require a pull request before merging**:
     - Approvals: `1`
     - Dismiss stale approvals on push: `Yes`
     - Require review from Code Owners: `Yes`
     - Require conversation resolution: `Yes`
   - Check **Require status checks to pass**:
     - Add the 8 checks listed above.
     - Require branches to be up to date: `Yes`
5. Click **Create**.

---

## 4. GitHub CLI (`gh`) Automation Snippet

For automated provisioning via GitHub CLI:

```bash
# Verify gh authentication
gh auth status

# Create or update branch protection via GitHub API
gh api \
  --method PUT \
  -H "Accept: application/vnd.github+json" \
  /repos/:owner/:repo/branches/main/protection \
  -f required_status_checks[strict]=true \
  -F "required_status_checks[contexts][]=Secrets & Gitleaks Audit" \
  -F "required_status_checks[contexts][]=Container & Dependency Vulnerability Scan (Trivy)" \
  -F "required_status_checks[contexts][]=Code Quality & Ruff Linter" \
  -F "required_status_checks[contexts][]=Static Type Check (Pyright)" \
  -F "required_status_checks[contexts][]=Hardcode & Secret Hygiene Check" \
  -F "required_status_checks[contexts][]=Living Documentation Drift Audit" \
  -F "required_status_checks[contexts][]=Architecture Diagram Verification" \
  -F "required_status_checks[contexts][]=Canonical Test Matrix (Pytest)" \
  -f enforce_admins=true \
  -f required_pull_request_reviews[dismiss_stale_reviews]=true \
  -f required_pull_request_reviews[require_code_owner_reviews]=true \
  -f required_pull_request_reviews[required_approving_review_count]=1 \
  -f required_linear_history=true \
  -f allow_force_pushes=false \
  -f allow_deletions=false
```

---

## 5. Verification Checklist

| Invariant Verification Item | Verified State | Enforcement Mechanism |
|---|:---:|---|
| Direct push to `main` without PR | Blocked | GitHub Branch Protection |
| Direct push to `main-clean` without PR | Blocked | GitHub Branch Protection |
| PR merge with unapproved CODEOWNERS | Blocked | GitHub CODEOWNERS Gate |
| PR merge with failing Pytest / Pyright | Blocked | GitHub Required Status Check |
| PR merge with hardcoded secrets or prices | Blocked | Gitleaks & scripts/hardcode-check |
| PR merge with drift between docs and code | Blocked | scripts/docs-drift Check |
| PR merge with non-linear merge commits | Blocked | Linear History Gate |
| Force push attempt (`git push --force`) | Rejected | Server-side Hook |
