## Overview

The system is designed to be extensible and adaptable across research, training, and external system integration use cases.

👉 See the [Codebase Reference](../codebase_reference.md) section for software architecture default, major components and, and data flows.

## Requirements Checklist

DCS-SE is designed to support:

- **A base set of environments + characters** with default configurations that server internal use cases but are extensible
- **Gameplay style extensibility** so the core engine can be integrated with other front ends like VR, audio RPG style interactions, etc. and support synchronous interaction patterns as well as turn-based.
- **AI research workflows** (training & evaluation) including static and open-ended systems and agents mediating between DCSs (interfacing agents)
- **Psych research workflows** (training & evaluation) with human participants
- **Education and leadership training** use cases that expose neurotypical humans to neurodivergent simulated characters
- **Reproducible results** via re-running w/ fingerprinted configs and deterministic runs