# Rules Configuration Guide

## Rule model

Each rule contains:

- `name`
- `document_types` (financial/legal/hr/medical/technical)
- `rule_type` (`format`, `logic`, `semantic`)
- `target_field`
- Optional constraints: `pattern`, `min_value`, `max_value`, `expression`
- `severity` (`info`, `warning`, `critical`)
- `enabled`
- `version`

## Manage via API

- List active rules:
  - `GET /rules?actor_role=analyst&enabled_only=true`
- Create rule:
  - `POST /rules`
- Update rule (creates new version):
  - `PUT /rules/{rule_id}`
- Bulk import:
  - `POST /rules/import/csv`

## CSV import format

Header:

```text
name,document_type,rule_type,target_field,pattern,min_value,max_value,severity,description
```

Example:

```text
INN Rule,financial,format,counterparty_inn,,, ,critical,INN checksum
Amount floor,financial,format,total_amount,,0,,critical,Amount should be non-negative
```

## Manage via UI

Open `http://localhost:5177` and use **Rules Studio** section to:

- Create single rules
- Import CSV text
- Inspect current active rules and versions
