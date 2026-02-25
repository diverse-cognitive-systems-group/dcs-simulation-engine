# Usability Analysis

An analysis of interfaces to ensure they are easy to use, understand, and reduce usability related confounds prior to downstream experimental usage. 

## Workflow

Upon major interface changes, re-run the usability analysis as follows:

1) Execute the run config

Run execution uses the installed dcs-se from this run’s environment. It produces results and metadata for reproducibility.

```sh
dcs run --config run.yaml
```

Outputs:
	•	results/ → full run data (ignored; may contain PII)
	•	metrics.json → summarized results (tracked)
	•	run.meta.json → metadata for reproducibility

⸻

2) Move results to secure storage

If results contain sensitive data (PII, human consent forms, etc.), move them to secure storage and update run.meta.json with the new location.

Perform analysis from secure storage mount.

4) Analyze results

Analysis is executed in the same run environment (so notebooks have the right deps):

```sh
uv run jupyter lab
```
