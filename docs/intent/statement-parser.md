# Hisaab core: parsing, allocation, and settlement

Status: scope confirmed by the user. Linear is the source of truth for implementation planning and task progress; pending technical and financial decisions remain explicit review gates.

## Outcome

Reconcile all credit-card statements for a month in one place: extract every entry, assign funding sources, combine amounts across cards, and track contributions. Spending categories support later analysis; funding allocations determine where money should come from to cover each expense. Do not require users to unlock PDFs manually.

## Users and privacy

The first database milestone serves only the primary user through a trusted local CLI using private direct database credentials. That authenticates a database role, not an individual application user. Do not enable a second user or distribute these credentials until authenticated isolation is implemented.

The eventual product serves the user and their wife through separate logins. Neither can access the other's cards, statements, transactions, allocations, settlements, or learned corrections. Allow additional users later without changing this ownership principle.

## First implementation slice

- Support the supplied YES Bank, SBI, HDFC Regalia, and HDFC Swiggy statement layouts.
- Use pdfplumber for local PDF extraction, with bank-specific parsing rules producing a common transaction format.
- Preserve every entry: purchases, payments, refunds, fees, interest, taxes, and other entries that cannot yet be classified.
- Record entry type separately from debit/credit direction. Repayments must not be counted as spending.
- Retain ambiguous entries and flag them for review. Do not invent missing dates or other unclear details; retain available descriptions and amounts.
- Suggest spending categories and funding sources independently, allow corrections, and remember those corrections for future suggestions. A category does not determine a funding source automatically.
- Validate parsing against all four sample statements. Successful text extraction alone does not establish transaction accuracy.

## Allocation and monthly settlement

These requirements extend the local core beyond the initial parsing milestone:

- Each entry can have one funding source, or remain unassigned pending review. Splitting one transaction across funding sources is deferred.
- Funding sources can represent bank accounts, budget pots, or people. They are distinct from the card used and from spending categories.
- Run reconciliation once all statements for the month are ready. Include all of that user's cards' statements for that reconciliation month; no manual statement-selection step is required.
- Tag each statement to the calendar month in which the bank generated/issued it, using its printed generation/issue (statement) date, not purchase dates, payment due dates, upload time or parser-run time. This rule applies to every month; January was only an illustrative example, not a fixed reconciliation period. Preserve each entry's original statement and card association.
- Combine allocations across cards into one monthly total per funding source, enabling one contribution rather than separate contributions for each card.
- Mark the monthly funding-source group settled when that source has contributed its share. Settlement does not mean the credit-card bill has been paid.
- Hisaab records settlement; it does not move money. The bank account receiving contributions is not relevant to this workflow.
- Monthly reconciliation remains owner-scoped and must not reveal the other user's private records.

## Password handling

The local experiment prompts for passwords with hidden input and does not save them. The eventual automated product will save a password per card, encrypted, without logging passwords or committing them to Git. Secure password persistence is not part of the first local parser slice.

## Broader product decisions

These are confirmed requirements, not features delivered by the local parser:

- Fetch statements from email, parse and deduplicate imports, categorize spending, and support later trend analysis.
- Use Supabase as the cloud data platform, with database-enforced user isolation.
- Retain original statements privately for a configurable number of calendar months from the statement date. Twenty-four months is a default, not a fixed limit. Cleanup is disabled by default; scheduling/deletion behavior and applying changes to existing PDFs need explicit review.
- Keep extracted data indefinitely.

## Approved database foundation

- Use Supabase/PostgreSQL directly, without an interim SQLite store.
- Use SQLAlchemy ORM and Alembic migrations, keeping parser dataclasses separate.
- Use five entities: Owner, Card, Statement, Import, and Entry. Statement is a logical bill; Import is a particular file/extraction. PDF bytes live on Import.
- Preserve UUID identities, exact money, file fingerprints, duplicate-looking entries, original evidence, and unresolved facts. Competing files must not silently replace the selected source.
- Keep connection configuration private in an owner-only, Git-ignored TOML file, shared by the app and migration tooling. Never store PDF passwords in the schema.
- Keep SQL/backend-specific migrations and security isolated. PostgreSQL is the first supported persistence backend; other engines require adapters/migrations and tests.
- Implement migrations and review them before applying to the hosted database. No schema creation on app startup.
- This foundation does not itself deliver the import command, no-op/candidate orchestration, reparse revisions, cleanup, or authenticated multi-user operation.

## Approved statement-loading increment

- Explicit owner/card registration and selection through the trusted local CLI.
- One immutable original-PDF snapshot for hashing, parsing, and binary storage; preserve original encryption and never reconstruct pages.
- Atomic writes per PDF, duplicate no-ops for the same owner/card/file hash, conservative competing-file candidates, and same-card concurrency handling.
- Preserve exact amounts, every row, evidence, and uncertainty. Summaries do not dump transactions or passwords.
- Restrict cloud-import inputs to the private project data directory. Explicit original retrieval and app-schema backups use fresh owner-only local exports.
- Verify native backup/restore with synthetic data. Review/merge and approve a controlled hosted smoke load before uploading private statements.
- No automatic retention deletion, candidate promotion/revision acceptance, or multi-user login is added by this increment.

## Approved static review workspace

- Host the static frontend on GitHub Pages. Use Supabase managed Auth and database APIs directly; no custom Python/Node application server or SSR hosting.
- Initially serve the primary user through Supabase Free email/password authentication. The page asks for application login credentials, never a database connection string/password or privileged API key.
- Link authenticated identity to the stable application Owner through a trusted setup path. Enforce permissions in database policies/API grants, not merely frontend filters. Bring this security work forward before browser data access.
- Provide two combined cross-card tables: a statement-date range includes every entry in matching statements, and a transaction-date range includes entries matching that date range. Preserve original card/statement associations. These review filters do not redefine reconciliation-month rules.
- Keep unknown dates and unresolved extraction issues visible through review paths without inventing inclusion dates. Separate competing imports from selected sources.
- Accounts mean budget/funding pots, such as Eating out or Furquan pocket money. They are not credit cards and need not be bank accounts. Categories are separate, even if names overlap.
- Manage accounts/categories and assign them independently to entries. Review supported issues through separately persisted decisions; preserve original extracted facts and PDF bytes. Decisions must survive reloads and appear consistently across both views.
- Keep raw PDF bytes out of ordinary table queries; evidence and original retrieval are explicit authorized actions. Never bake financial records into the static build or public logs.
- Suggestions, settlement calculations, browser-side PDF extraction, shared access, transfers, split allocations, budget-limit/balance tracking and automatic retention deletion are outside this first UI milestone.
- Existing CLI import and backup workflows remain supported. Real hosted loading remains a separately approved backup/smoke-validation gate.
- Scope and the React + TypeScript + Vite frontend stack are confirmed. Implementation sequencing, API security design and edit/filter details remain subject to review in [the staged delivery plan](https://linear.app/furquan/document/static-review-workspace-confirmed-intent-and-staged-delivery-57d96644cf6b). No browser access policies or UI implementation are implied by this intent update.

## Out of scope for the original local parser slice

Email fetching, Supabase integration, login and access-policy implementation, encrypted password persistence, automated retention cleanup, dashboards, trend analysis, and identifying the bank account paying a credit-card bill. Shared access between users is also out of scope.

Split allocations and actual money transfers are out of scope. Funding-source assignment is in scope; inferring the account paying a credit-card bill is not.

## Evidence and limits

The user supplied historical workbooks for 2024, 2025, and 2026 under private `data/reference/`. Their Account labels mix funding accounts, budget buckets, and people; Actual Amount columns handle signed credits or adjustments; Paid markers support reconciliation. The user confirmed that these markers mean funding contributions, historically settled separately per card. Hisaab should combine those contributions across cards. The workbooks are reference material, not an approved historical-import specification.

The existing local probe opened all four samples successfully. HDFC requires handling merged table columns and differing rewards columns; YES Bank has more distinct table columns; SBI merges multiple entries into cells and has entries without an independently visible date. Generic table extraction is not sufficient on its own.

Private PDFs and extracted results remain under Git-ignored `data/`. Commit only synthetic or carefully sanitized fixtures. Supporting one sample layout per card does not imply support for every historical or future statement format.

## Related documents

- [Hisaab project and task tracker](https://linear.app/furquan/project/hisaab-f672b4a38a9f)
- [Implementation reference and decision gates](https://linear.app/furquan/document/hisaab-implementation-reference-and-decision-gates-948f63b55975)
- [Statement parsing and imports: FUR-6](https://linear.app/furquan/issue/FUR-6)
- [Monthly allocation and settlement: FUR-5](https://linear.app/furquan/issue/FUR-5)
