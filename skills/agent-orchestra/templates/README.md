# Bundled template index

`INDEX.yaml` is a verbatim copy of `grok_orchestra/templates/INDEX.yaml` —
the canonical catalogue. `INDEX.json` is the JSON translation that
`scripts/choose_template.py` reads at runtime (chosen over YAML so the
skill needs no `pyyaml` dependency in the Claude Code environment).

## Sync contract

`tests/test_skill_index_in_sync.py` asserts that `INDEX.json` is the
canonical translation of `INDEX.yaml` (which is itself byte-equal to
the upstream catalogue). Bumping the canonical INDEX is a two-step:

1. Update `grok_orchestra/templates/INDEX.yaml`.
2. Regenerate the bundled copies:

   ```bash
   cp grok_orchestra/templates/INDEX.yaml \
      skills/agent-orchestra/templates/INDEX.yaml
   python -c "import yaml, json; \
     d = yaml.safe_load(open('grok_orchestra/templates/INDEX.yaml')); \
     json.dump(d, open('skills/agent-orchestra/templates/INDEX.json', 'w'), \
               indent=2, sort_keys=False)"
   ```

The CI sync test fails fast if the bundled JSON drifts from the YAML.
