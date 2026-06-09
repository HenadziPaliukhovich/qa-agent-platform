# Thin Slice — GitHub Issues and ADR Backlog

## GitHub issues

### Epic 1 — Domain model foundation

#### Issue 1. Create DB schema for domains and domain profiles
**Goal:** Introduce `domains` and `domain_profiles` tables as first-class product entities.

**Scope:**
- Add migration for `domains`.
- Add migration for `domain_profiles`.
- Define constraints, timestamps, status fields, and JSONB config fields.
- Keep backward compatibility with existing schema.

**Definition of done:**
- Local migration works.
- Tables exist in Postgres.
- Schema documented in tech notes or ADR references.

#### Issue 2. Implement Domains CRUD API
**Goal:** Add API endpoints to create, list, read, update, and archive domains.

**Scope:**
- `POST /api/domains`
- `GET /api/domains`
- `GET /api/domains/{domain_id}`
- `PUT /api/domains/{domain_id}`
- `POST /api/domains/{domain_id}/archive`

**Definition of done:**
- Domain lifecycle works end-to-end via API.
- Archived domains are not deleted physically.

#### Issue 3. Implement Domain Profile API
**Goal:** Allow storing and updating configurable domain behavior.

**Scope:**
- `GET /api/domains/{domain_id}/profile`
- `PUT /api/domains/{domain_id}/profile`
- Support fields for business scope, prompt policy, retrieval policy, supported artifacts, event source settings, integration bindings.

**Definition of done:**
- One profile per domain is supported.
- Profile is editable via API.

### Epic 2 — Domain context management

#### Issue 4. Create DB schema for domain context files and chunks
**Goal:** Introduce domain-scoped context storage.

**Scope:**
- Add `domain_context_files` table.
- Add `domain_context_chunks` table.
- Include soft-delete or status fields.
- Include metadata and token estimates.

**Definition of done:**
- Schema exists and supports one-to-many domain → context file → chunks.

#### Issue 5. Implement Domain Context File CRUD API
**Goal:** Let users add, view, edit, and delete context files inside a domain.

**Scope:**
- `POST /api/domains/{domain_id}/context-files`
- `GET /api/domains/{domain_id}/context-files`
- `GET /api/domains/{domain_id}/context-files/{context_file_id}`
- `PUT /api/domains/{domain_id}/context-files/{context_file_id}`
- `DELETE /api/domains/{domain_id}/context-files/{context_file_id}`

**Definition of done:**
- Text-based context files can be created and managed.
- Delete uses soft-delete behavior.

#### Issue 6. Implement chunking pipeline for domain context files
**Goal:** Ensure uploaded context becomes retrievable.

**Scope:**
- Reuse or adapt existing chunking logic from current RAG service.
- Generate chunks on create/update.
- Rebuild chunks when context file content changes.

**Definition of done:**
- Each active context file has corresponding active chunks.

### Epic 3 — Domain-aware retrieval and execution

#### Issue 7. Refactor RAG service to support domain-scoped retrieval
**Goal:** Retrieval must be limited to the selected domain by default.

**Scope:**
- Add retrieval by `domain_id`.
- Optionally support `selected_context_ids`.
- Return source references for used chunks.
- Prevent cross-domain retrieval unless explicitly designed later.

**Definition of done:**
- Retrieval for thin slice only returns context from one domain.

#### Issue 8. Extend task schema and task API with `domain_id`
**Goal:** Make domain selection part of task execution.

**Scope:**
- Add `domain_id` to task creation request.
- Add optional `context_scope` and `selected_context_ids`.
- Persist new fields in DB.

**Definition of done:**
- New task flow supports domain-aware execution.
- Legacy flow remains functional during transition, if needed.

#### Issue 9. Update orchestrator to run domain-aware execution flow
**Goal:** Pass domain and context metadata through the execution pipeline.

**Scope:**
- Read `domain_id` from task payload.
- Fetch domain-scoped context.
- Inject context into generation chain.
- Preserve task status lifecycle.

**Definition of done:**
- `requirements_analysis` can execute inside a chosen domain.

#### Issue 10. Update result service to persist used-context snapshot
**Goal:** Improve explainability and trust in generated artifacts.

**Scope:**
- Extend result/artifact persistence with `domain_id`.
- Store `used_context` references in artifact or task result.
- Ensure result view can display source references.

**Definition of done:**
- Generated result clearly shows which context chunks were used.

### Epic 4 — Thin-slice frontend

#### Issue 11. Build Domains list page
**Goal:** Let users browse and manage domains.

**Scope:**
- Show name, description, tags, status, context count.
- Add actions for create/open/archive.

**Definition of done:**
- Domains are visible and navigable through UI.

#### Issue 12. Build Create/Edit Domain page
**Goal:** Let users configure domains from UI.

**Scope:**
- Form fields: name, slug, description, tags, business scope, retrieval policy, prompt policy.
- Support create and update modes.

**Definition of done:**
- User can create and edit domain metadata and profile via UI.

#### Issue 13. Build Domain Context page
**Goal:** Let users manage context files for one domain.

**Scope:**
- List context files.
- Add new text-based context file.
- Edit context file.
- Delete context file.
- Preview content.

**Definition of done:**
- Context file lifecycle works fully from UI.

#### Issue 14. Build Run Task page
**Goal:** Let users launch the first domain-scoped task from UI.

**Scope:**
- Domain selector.
- Task type selector.
- Input text area.
- Context scope selector.
- Optional explicit context selection.

**Definition of done:**
- User can run `requirements_analysis` in a selected domain.

#### Issue 15. Build Task Result view
**Goal:** Show output and explainability data.

**Scope:**
- Display task metadata.
- Display normalized output.
- Display domain info.
- Display used context references.

**Definition of done:**
- User can inspect generated result and its source context.

### Epic 5 — Stabilization and developer enablement

#### Issue 16. Add thin-slice integration tests
**Goal:** Verify the first vertical slice works end-to-end.

**Scope:**
- Test domain creation.
- Test context upload.
- Test domain-scoped retrieval.
- Test task execution.
- Test result persistence with used-context references.

**Definition of done:**
- Thin-slice flow covered by automated tests.

#### Issue 17. Add seed data / demo script for thin slice
**Goal:** Make the slice easy to demo locally.

**Scope:**
- Seed at least one example domain.
- Seed sample context files.
- Provide a script or documented steps.

**Definition of done:**
- Demo can be launched quickly in local environment.

#### Issue 18. Update docs for thin slice setup and usage
**Goal:** Keep implementation discoverable and maintainable.

**Scope:**
- Update README or docs.
- Describe new APIs.
- Describe UI flow.
- Add notes on migration from old model.

**Definition of done:**
- Another contributor can run and understand the thin slice.

## ADR backlog

### ADR 1. Domain as first-class product entity
**Decision to capture:**
- Why domains become a primary product concept.
- Why domains are configurable from UI.
- Why domain list must not live only in code.

**Key questions:**
- What belongs to `Domain` vs `DomainProfile`?
- What domain behavior is configurable vs code-defined?

### ADR 2. Migration from `project/service_name` to `domain/profile/context`
**Decision to capture:**
- How to evolve current knowledge and task model without breaking the existing skeleton.
- Whether transition is additive, staged, or replacement-based.

**Key questions:**
- Do we preserve `project_id` temporarily?
- How do old documents map to new domain context?

### ADR 3. Domain context storage model
**Decision to capture:**
- How context files and chunks are stored.
- Why soft-delete is preferred.
- Whether edits are versioned or in-place in thin slice.

**Key questions:**
- Is file storage text-first initially?
- When do we introduce binary file ingestion and object storage?

### ADR 4. Domain-scoped retrieval policy
**Decision to capture:**
- Why retrieval is restricted to one selected domain by default.
- How explicit context selection works.
- Why cross-domain retrieval is out of scope initially.

**Key questions:**
- What is the default retrieval scope?
- How do we expose used-context references?

### ADR 5. Task execution contract with `domain_id`
**Decision to capture:**
- How tasks become domain-aware.
- Which task fields are mandatory in the new execution path.
- How backward compatibility is handled during migration.

**Key questions:**
- Is `domain_id` required for all new tasks?
- Do we support a temporary legacy path?

### ADR 6. Result artifact explainability contract
**Decision to capture:**
- What minimal explainability data each artifact must store.
- Why `used_context` becomes part of the result contract.

**Key questions:**
- What level of context detail should be persisted?
- Do we store chunk IDs only or chunk previews too?

### ADR 7. Thin-slice UI architecture
**Decision to capture:**
- How the frontend should structure thin-slice screens and state.
- Whether to use server state caching, local forms, and route structure in a consistent way.

**Key questions:**
- What is the route map for domains, context, tasks, and results?
- How much profile configuration is exposed in v1 UI?

## Recommended execution order

1. ADR 1 — Domain as first-class product entity.
2. ADR 2 — Migration from `project/service_name` to `domain/profile/context`.
3. ADR 3 — Domain context storage model.
4. Issue 1 — DB schema for domains and profiles.
5. Issue 4 — DB schema for context files and chunks.
6. Issue 2 — Domains CRUD API.
7. Issue 3 — Domain Profile API.
8. Issue 5 — Context File CRUD API.
9. Issue 6 — Chunking pipeline.
10. ADR 4 — Domain-scoped retrieval policy.
11. Issue 7 — RAG service refactor.
12. ADR 5 — Task execution contract with `domain_id`.
13. Issue 8 — Task API update.
14. Issue 9 — Orchestrator update.
15. ADR 6 — Result artifact explainability contract.
16. Issue 10 — Result service update.
17. Issue 11–15 — Frontend implementation.
18. Issue 16–18 — Stabilization, demo, docs.