# Scenario kits

Scenario kits connect existing Platform tools into a focused workflow. A Lab can enable multiple kits; its Projects can apply them independently. Samples, Protocols, Records, access control and analysis remain ordinary Platform assets.

## First workflow

The bundled **Samples and numerical results** kit supports:

1. A Lab Owner or Manager enables a version in **Lab settings → Scenario kits** after reviewing the destination and impact.
2. A Project manager opens **Scenario workbench**, previews the application and confirms. The first application also requires Lab resource management permission to create the shared sample type.
3. Register samples with a name, unique Lab code, category and optional source/storage conditions. Existing sample/resource permissions apply. Samples belong to the Lab library and may be reused across Projects; the workbench list is explicitly Lab-wide.
4. Select samples and download a results CSV. Only sample references are filled. Enter the actual method, metric, finite numeric value, unit and measurement time. Version 1.1.0 adds optional notes; version 1.0.0 remains available.
5. Upload through the existing Record importer. Keep canonical `var.*` headers; validate, review and confirm. A validation error creates no Records. Correct the file and retry; there is no staging/draft import module.
6. Alternatively, fill the normal sample measurement Protocol manually. Resource links pin sample revisions; each Record retains its Protocol version.
7. Open analysis. The editable default groups by **method, metric and unit**, and rejects missing numeric inputs. Review the actual Record scope and calculation recipe, then confirm. Existing analysis history, source manifests, report export and saved methods apply.

These steps do not require AI or an external model provider. The kit does not interpret assays, normalize physical units, infer missing measurements or generate scientific conclusions. Different methods/metrics/units remain separate groups; the user must further distinguish experiments when their scientific context requires it.

**Material samples and numerical results** is a second composition of the same modules. It shares sample identities with the first kit and provides an independent editable measurement Protocol. It does not implement chemical structures, stoichiometry, or a chemistry-specific interpretation engine.

## Versions and deactivation

- Template assets are copies with their source kit version, original ProtocolVersion and content digest recorded in application receipts. Ordinary edits do not modify the bundled catalog.
- Apply/upgrade offers **keep existing templates** or **create a new template copy**. Neither overwrites user edits or historical Records. The workbench can select older accessible copies.
- Previews bind the user, target scope, installed revisions, manifest digest and current Protocol content for 15 minutes. Changes require a fresh preview. Confirmation request IDs make retries idempotent.
- Lab-level changes are serialized. Failed compilation/storage/authorization rolls back database assets and attempts to remove uploaded temporary packages.
- A Lab kit cannot be disabled while a Project application is active. Project deactivation is blocked while research or analysis work is unfinished. Deactivation closes kit-specific actions; existing ordinary Protocols, resource views, Records and analyses retain their normal access paths. It is not a global prohibition on using those assets.
- Receipts cannot be edited or individually deleted. Parent Lab/Project deletion may remove scoped receipts through the existing authorized deletion workflow; other scientific retention constraints still apply. Managers can export the most recent 200 operation receipts, with no source data included.
- The shared sample schema must remain compatible. The service refuses to silently replace an archived/changed type or appropriate a pre-existing reserved sample type code.

## Administration and extension boundary

`SCENARIO_KIT_MODULES` is an instance allowlist. Its default is `airalogy.samples,airalogy.records,airalogy.analysis`; an empty value disables kit activation and actions. This does not revoke access to ordinary assets. API checks enforce membership, scope, module availability and permissions regardless of visible UI controls. Public Project visibility does not expose private Lab samples or kit configuration to nonmembers.

This release accepts only built-in, versioned manifests and trusted templates shipped in the application. There is no upload-and-execute plugin installer, shared external database, external scheduler, or automatic grant of permissions. Add future official kits through reviewed catalog entries, compatibility tests and normal Platform releases. Any external extension ecosystem requires its own reviewed contracts and acceptance work, as tracked in [RFC #12](https://github.com/airalogy/platform/issues/12).

## Software acceptance and trial boundary

Use only synthetic fixtures for automated verification. The reference calculation imports values `2 mg/L`, `4 mg/L` and `100 g/L` for one synthetic method/metric: the two group means are `3 mg/L` and `100 g/L`. An unfilled CSV must fail without creating a Record.

Backend acceptance uses the real Protocol compiler, PostgreSQL, object storage, Record importer, resource references and analysis worker. Browser acceptance covers Lab enablement, Project application, registration, template download, import validation, report generation, language switching and a narrow viewport with AI disabled.

No specific pilot assay or instrument file was supplied. Real laboratory acceptance, assay rules, instrument-specific import adapters, chemical modules and third-party extension installation remain separate follow-up work; synthetic acceptance is not scientific validation.
