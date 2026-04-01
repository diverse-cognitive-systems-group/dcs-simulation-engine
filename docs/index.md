# DCS Simulation Engine Documentation

The simulation engine is a tool designed and developed by the Diverse Cognitive Systems (DCS) group at Georgia Tech under the [Sonification Lab](http://sonify.psych.gatech.edu/) to facilitate training and evaluation of interactions between diverse cognitive systems.

Specifically, the DCS group aims to recognize, understand and engineer diverse cognitive systems, including but not limited to *neurodivergent humans, artificial intelligences, hybrid systems, basal and somatic intelligence and other forms that diverge much more from anthropocentric norms.*

## Conceptual Foundations
In this project, Diverse Cognitive Systems (DCS) refers to any kind of cognitive agent—biological, artificial, hybrid, or otherwise. (Other fields might use terms like diverse intelligences; for our purposes, these are interchangeable.)

Our work depends on an environment that can simulate interactions between these systems with high behavioral representational fidelity. This is necessary both for training new agents and for evaluating or benchmarking existing ones across a range of scenarios. Currently, there is no established framework for understanding or assessing how well cognitive systems engage as goalspace, function and form change. At the same time, people are rapidly engineering new cognitive systems (e.g., AI) without really understanding or measuring how well they can understand or engage outside of anthropocentric norms.

The simulation engine is designed specifically to address this gap: it provides a configurable environment populated with [core characters](core_characters.md), each representing a cognitive system with different capacities (e.g. goals, sensory, perceptual, regulatory, and motor/action modalities). These characters can be used to simulate interactions in a variety of scenarios.

Scenarios within the simulation engine are called “games” which provide control the structure/flow of interactions. They can be adapted or reconfigured depending on the research question. We include a set of [core games](core_games.md) that are useful for our studies. For example, if we want to examine how accuracy rate of goal inference between two cognitive systems as their sensory, perceptual, regulatory, and motor/action capacities diverge from anthropocentric norms, we use the Goal Inference game.