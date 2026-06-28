# Post-Phase-2 Knowledge Base Commit Instructions

You are at this state:

```txt
48fb757 (HEAD -> main, origin/main, origin/HEAD) Add Phase 2G dry-run publisher packages
44 tests passed
```

## 1. Add the knowledge files

Copy the `docs/knowledge/` folder from this package into the repo root:

```txt
C:\repos\Shorts Factory\docs\knowledge\
```

## 2. Do not commit generated artifacts

Leave this untracked unless you intentionally want to preserve it:

```txt
output/jobs/d1be5b686709/
```

## 3. Decide what to do with root handoff/receipt files

Current untracked files reported:

```txt
PHASE_2A_RECEIPT.md
SHORTS_FACTORY_KNOWLEDGE_BASE_AND_AUTONOMOUS_GOVERNANCE_HANDOFF (1).md
```

Recommended:

- Do not commit the handoff file unless you want repo-local handoff history.
- If `PHASE_2A_RECEIPT.md` contains details not already in `docs/knowledge/PHASE_RECEIPTS.md`, copy them into the knowledge file first.
- Then either delete it or intentionally commit it.

## 4. Validate

```powershell
cd "C:\repos\Shorts Factory"
pytest -q
git status --short --branch
```

## 5. Commit knowledge base

```powershell
git add docs/knowledge
git commit -m "Add post-Phase-2 knowledge base and governance"
git push
```

## 6. Optional milestone tag

After the commit is pushed:

```powershell
git tag v0.2-phase2-complete
git push origin v0.2-phase2-complete
```

## 7. Stop

Do not start Phase 3 until the user chooses the next direction.
