# Analyze Gameplay Results

⚠️ Note: This page is incomplete and/or missing information.

Engine runs produce results that contain all the raw data from the run including the whole database, logs and metadata so the run is reproducible (useful for research user cases).

> Note: the results can be dumped/exported at any time during a run using the `dcs save` command, however by default its exported at the end of the run.

## Generate report

A report that contains key metrics and visualizations summarizing the run can be generated with the command below. The report is customizable and extensible, and you can add your own custom analyses and visualizations to it. 

For a deeper analysis of results, you can checkout the code and use the manual analysis notebooks that the DCS group uses internally or create your own.

```bash
dcs report <path/to/results>
```

### Custom Reports

DCS group uses custom reports for studying the usability, simulation quality and performance benchmarking various AI players. 