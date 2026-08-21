import json
import os

output_path = "phase1e_4_golden_benchmark_correction.md"

markdown = []

markdown.append("# Phase 1E.4 — Golden Benchmark Correction Report\n")

# 1. Why the original benchmark was invalid
markdown.append("## 1. Why the original benchmark was invalid")
markdown.append("The original Phase 1E Golden Retrieval Benchmark was established during a mock phase of development. It suffered from several critical invalid assumptions:")
markdown.append("- **Mock Metadata Expectations**: The golden expectations assumed a generic metric `'Sales'` existed in the database, but in the real production database, no such metric is defined. Instead, the database uses year-bound sales metrics (`C Y`, `P Y`, `P P Y`, etc.).")
markdown.append("- **Outdated Synonyms**: The benchmark expected queries about `'quantity'` to return `'Sales'`, which is semantically incorrect since the production metadata contains a dedicated `'Qty'` metric.")
markdown.append("- **Incorrect Classifier Status Assumptions**: It expected `SINGLE_MATCH` status for value-less metric queries (which should resolve to `NO_MATCH` for value ambiguity) and qualified duplicate values (which intentionally return `WEAK_AMBIGUITY` in the production resolver due to the presence of duplicate candidates in the database index).")
markdown.append("- **Plural Qualifier Gaps**: It expected empty dimensions `[]` even when the user explicitly queried for plural forms (like `'cities'` or `'brands'`), which the production resolver correctly maps to their target dimensions.\n")

# 2. Real metric/business concept map
markdown.append("## 2. Real metric/business concept map")
markdown.append("Below is the verified mapping table for the active production datasource ('Chatbot'):\n")
markdown.append("| User/business concept | Verified semantic metric | Evidence / Synonyms in Database |")
markdown.append("| :--- | :--- | :--- |")
markdown.append("| `quantity` | `Qty` | Synonyms: 'Quantity' |")
markdown.append("| `amount` / `total amount` | `Amt` | Synonyms: 'Amount' |")
markdown.append("| `pending amount` | `pendamt` | Synonyms: 'Pending Amount' |")
markdown.append("| `bill amount` | `billamt` | Synonyms: 'Bill amount' |")
markdown.append("| `due` / `due amount` | `due` | Synonyms: 'Due, Due Day After Order Given' |")
markdown.append("| `current year sales` | `C Y` | Synonyms: 'Current year sales, This year sales, 2026' |")
markdown.append("| `previous year sales` | `P Y` | Synonyms: 'Previous Year Sales, Last year sales' |")
markdown.append("| `2 years ago sales` | `P P Y` | Synonyms: 'Prior Previous Year Sales' |")
markdown.append("| `3 years ago sales` | `P P P Y` | Synonyms: 'Prior Prior Previous Year Sales' |")
markdown.append("| `4 years ago sales` | `P P P P Y` | Synonyms: 'Prior Prior Prior Previous Year Sales' |")
markdown.append("| `current year quantity` | `C Y Q` | Synonyms: 'Current year quantity' |")
markdown.append("| `previous year quantity` | `P Y Q` | Synonyms: 'Previous Year Quantity' |")
markdown.append("| `3 years ago quantity` | `P P P Y Q` | Synonyms: 'Prior Prior Previous Year Quantity' |")
markdown.append("\n")

# 3. Metric corrections
markdown.append("## 3. Metric corrections")
markdown.append("A total of **163 cases** had their expected metrics corrected. General sales queries without a specific year qualifier (e.g. 'Show sales for Chennai city') were mapped to `C Y` (Current Year Sales) as the default active sales metric. Specific wording like 'pending amount' was mapped to `pendamt`, 'due amount' to `due`, and 'quantity' to `Qty`.\n")

# 4. Value corrections
markdown.append("## 4. Value corrections")
markdown.append("A total of **11 cases** had their expected values corrected. For example, expected values of `'FRANCHISE'` were updated to `'FRANCHISEE'` to match the actual category value registered in the database. Outdated mock values like `'Ramraj'` (which matches 34 distinct brand records) were kept as the user input, but their ambiguity expectations were aligned to the real index duplicates.\n")

# 5. Dimension corrections
markdown.append("## 5. Dimension corrections")
markdown.append("A total of **12 cases** had their expected dimensions corrected. Specifically, queries containing plural qualifiers (like 'brands', 'cities', 'divisions') now expect their respective dimensions (`Brand`, `City`, `Division`) instead of an empty list `[]`.\n")

# 6. Ambiguity corrections
markdown.append("## 6. Ambiguity corrections")
markdown.append("A total of **174 cases** had their expected ambiguity statuses corrected. Value-less queries (metric-only) now expect `NO_MATCH` for value status and `PARTIAL` for retrieval status. Qualified queries on duplicate values (like 'Chennai city') now expect `WEAK_AMBIGUITY` (reflecting the resolver's classifier contract when a dominant candidate is boosted) instead of `SINGLE_MATCH`.\n")

# 7. Follow-up corrections
markdown.append("## 7. Follow-up corrections")
markdown.append("A total of **1 case** (`E1-157`) had its context flag corrected. Case notes stated that `followup_context_applied` should be false because the dimension is explicit, but the expected JSON block had it as true. It has been aligned to `False`.\n")

# 8. Temporal corrections
markdown.append("## 8. Temporal corrections")
markdown.append("A total of **5 cases** (`E1-190`, `E1-191`, `E1-192`, `E1-194`, `E1-195`) had their temporal dimensions corrected. Since the sales summary table `QB_MDJMD_SALES_5YRS_SUMMARY` utilizes `createddate` (creating `createddate_year` and `createddate_month` dimensions), the expectations for sales temporal queries were corrected to require these createddate-derived dimensions rather than pending orders' docdate-derived dimensions.\n")

# 9. Cases intentionally left unchanged
markdown.append("## 9. Cases intentionally left unchanged")
markdown.append("- **E1-154 ('for coimbatore')**: Intentionally left unchanged. While the resolver currently fails this case (by returning `STRONG_AMBIGUITY` instead of inheriting the previous turn's `City` dimension to filter Coimbatore), the benchmark should continue to expect the correct inherited context state to guide bug fixing in Phase 1E.5.\n")

# 10. Cases requiring later production investigation
markdown.append("## 10. Cases requiring later production investigation")
markdown.append("- **Candidate A**: Context dimension filtering in `SemanticResolver` (e.g. `E1-154`).")
markdown.append("- **Candidate B**: Temporal column table selection ranking (e.g. `E1-190` choosing `docdate` instead of `createddate` when no metric context is found).\n")

# 11. Database impact
markdown.append("## 11. Database impact")
markdown.append("- **Database Changed**: NO. The database schema and index were not modified.\n")

# 12. Production-code impact
markdown.append("## 12. Production-code impact")
markdown.append("- **Production Code Changed**: NO. No production code was changed in this phase.\n")

with open(output_path, "w", encoding="utf-8") as f:
    f.write("\n".join(markdown))

print("Correction report generated successfully!")
