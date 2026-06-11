# Volunteer Roadmap: OncoMX & SenNet Curation

This document is your primary reference for the project. Each week has enough detail to work independently - read the full week before starting. If something is unclear, ask before proceeding rather than making assumptions.

---
## Week 1 (complete) - Kick-off and onboarding

## Week 2 - Environment and tooling setup
- Register on GitHub (if not already) and share your username
- Get access to the biomarker-qc repository; clone it and confirm `biomarker-qc.py` runs on your machine
- Read through the README so you understand what checks the script currently runs
- Familiarize yourself with both TSV files (`oncomx.tsv` and `sennet.tsv`) - just browse them, no changes yet
- Define the contribution workflow: you'll document issues and proposed corrections in a corrections file (CSV with columns for row number, field, current value, proposed value, and reasoning); direct TSV edits are handled by the mentor

## Week 3 - OncoMX: Programmatic issue discovery

### Context
The standalone QC module you've been using was extracted from a larger codebase called `format-converter`. This week you'll move that work into its proper home: the [data-qc repo](https://github.com/clinical-biomarkers/data-qc). The logic is the same - you're just giving it a version-controlled, collaborative home where you'll build on it going forward.

### Instructions
1. **Fork the data-qc repo** and set it up locally. If you're unfamiliar with forking, GitHub's [documentation](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/working-with-forks/fork-a-repo) is a good starting point.
2. **Port your existing checks** from the standalone module into the data-qc repo. Don't copy-paste blindly - read each check and make sure you understand what it's testing before you add it.
3. **Extend the checks** to catch patterns the existing script misses. Specifically look for:
   - Conflicting accessions or entity types for the same ID
   - Mismatched biomarker strings - e.g. `LYMP` vs `LMYPH` (these should be the same thing but appear differently due to data entry errors)
4. Run your extended checks on `oncomx.tsv` and produce an **annotated issue report**: a log listing every detected issue with its row number, field, and a short description of the problem.

### What good output looks like
A report where someone can look up any flagged row and immediately understand what the problem is without re-reading the whole file. Row number, field name, and a plain-English description of the issue for each entry.

## Week 4 - OncoMX: Deep row-by-row review

### Context
Last week's checks found issues programmatically - they caught patterns. This week you're doing the judgment work: reading flagged rows carefully, deciding what the correct value should be, and documenting your reasoning. This is slower and more demanding than running a script. Take your time.

### Instructions
1. Work through the issues flagged in your week 3 report **one by one**. For each issue, add an entry to the correction log with: row number, field, current value, proposed correct value, and your reasoning in plain English.
2. Focus first on these known problem categories:
   - **ID/panel collapse problems:** `LYMP`/`LMYPH`, `platelet`/`thrombocytopenia`, `SAA1` - these are cases where the same biological concept appears under different names and may need to be reconciled.
   - **Wrong disease names:** check against the Disease Ontology (DOID). For example, a row with `DOID:1612` should match the correct disease label - if it doesn't, flag it.
   - **Wrong entity types:** e.g. a row marked as a gene where the accession points to a protein.
   - **Cross-field inconsistencies:** e.g. a copy number entry for HGF that references an IL6 entity - the fields don't agree with each other.
   - Examples of known issues can be viewed here: https://github.com/clinical-biomarkers/biomarker-issue-repo/issues/29
3. **Do not edit the TSV.** All corrections go in the log only.
4. At the Thursday office hours meeting, ask Jeet to review a sample of your proposed corrections. Have your log in a shareable state by then - even if it's incomplete.

### What good output looks like
A correction log where every entry has a clear, specific proposed value and a reasoning note that explains *why* the current value is wrong and *how* you arrived at the proposed one. Vague entries like "seems wrong" are not enough - cite the source or logic behind each correction.

## Week 5 - SenNet: Programmatic issue discovery & evidence extraction

### Context
SenNet has two main categories of issues: missing **directionality** in biomarker strings, and missing **evidence**. Directionality means whether a biomarker is increased, decreased, etc. - without it, the entry is incomplete. Evidence means the supporting sentence from literature that justifies the biomarker entry.

### Instructions
1. Run your QC checks on `sennet.tsv`. Flag:
   - All rows missing directionality in the biomarker field
   - All rows with empty evidence
   - Any other issues (wrong entity types, ID inconsistencies, etc.) - document these separately
2. Organize your findings into a **structured issue log**: categorize by issue type, include row references, and note whether each issue is a directionality gap, missing evidence, or something else.
3. **Add directionality** to biomarker strings where it's missing. Base this on the evidence text in the row - if the evidence says "SAA1 levels were elevated in senescent cells," the directionality is `increased`. If the evidence itself is missing, skip directionality for now and address it in the next step.
4. **Extract missing evidence** semi-manually: find the relevant paper for the row (the accession or existing context should point you there), feed it to a generative AI tool (e.g. ChatGPT, Claude), and ask it to extract the supporting sentence for that biomarker claim. **Always review the output** - do not paste AI-extracted evidence into the log without reading it against the source paper yourself. If you can't verify it, flag the row as needing review rather than filling it in.

### What good output looks like
A complete correction log for SenNet with every issue categorized, every directionality gap filled or flagged, and every missing evidence field either filled with a verified sentence or explicitly marked as unresolved with a note explaining why.

## Week 6 - Corrections & validation

### Context
This week you shift from documenting problems to codifying them. The manual review in weeks 4 and 5 surfaced issues that the script didn't catch - your job now is to close that gap. For every category of issue you found manually, there should be a check in the script that would have caught it automatically. The TSVs are not touched.

### Instructions
1. Go through your correction logs for both OncoMX and SenNet. For each issue category (ID/panel collapse, wrong disease names, wrong entity types, cross-field inconsistencies, missing directionality, missing evidence, etc.), ask: **would the current QC script have flagged this?** If not, write a check that would.
2. **Implement the new checks** in the data-qc repo. Each check should:
   - Target a specific, well-defined issue pattern
   - Output the affected row numbers and fields in the issue log
   - Include a short comment in the code explaining what it's catching and why
3. **Re-run the full QC script** on both `oncomx.tsv` and `sennet.tsv`. Verify that the issues you found manually now appear in the script output. If a known issue doesn't surface, the check isn't working - debug before moving on.
4. Any issues that are genuinely too ambiguous or context-dependent to automate should be noted explicitly in a **follow-up log** with an explanation of why they resist automation.

### What good output looks like
An updated QC script that catches everything the manual review found, a re-run output log showing those issues surfaced programmatically, and a short follow-up log of anything that couldn't be automated and why. Someone running the script cold on a future version of these files should catch the same classes of problems you found manually.

## Week 7 - Final Review & Wrap-Up

### Context
This is a consolidation week. The goal is to make sure nothing slipped through and that the project is in a state someone else could pick up and understand.

### Instructions
1. Do a final pass over both corrected TSVs and your residual issue logs. Look for anything that was flagged but not resolved, and make sure every open item is explicitly noted as unresolved (not just absent from the log).
2. Write a **short project summary** covering:
   - What QC checks were written and what they caught
   - What issues were found in OncoMX and SenNet, broken down by category
   - What was corrected and what remains unresolved, and why
   - Any patterns or surprises that future curators should know about
3. Use any remaining time as a buffer for anything that ran long or needs a second look.

### What good output looks like
A summary document that someone unfamiliar with the project could read and understand the state of both datasets without needing to dig into the logs. Clear, specific, and honest about what's still open.

## Week 8 - Symposium Presentation Prep

Prepare a short presentation summarizing the project for the symposium. Draw from your week 7 summary. Cover what the curation project was, how you approached it, what you found, and what was resolved vs. still open. Your mentor will advise on format and length.

## Standing Notes

- **Never edit the TSVs directly** except during week 6 when applying approved corrections.
- **When in doubt, ask.** It's always better to ask a question than to make an assumption that propagates through the rest of the work.
- **Cite your reasoning.** In the correction log, vague notes aren't enough — explain what source or logic led you to the proposed value.
- **AI-extracted evidence must be verified.** Always check AI output against the source paper before adding it to the log.
