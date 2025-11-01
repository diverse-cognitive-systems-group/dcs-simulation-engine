# Major Design Decisions

The Diverse Cognitive Systems (DCS) group at Georgia Tech is developing this simulation engine to study how to recognize, understand, and engineer diverse forms of cognition.

We needed a simulation environment capable of training and evaluating autotelic agents across radically different cognitive systems—ranging from neurodivergent humans to simple mechanical systems to alien-like intelligences.

To support that, we built a highly compute-efficient, flexible, and modular simulation engine using a textual, scenario-based approach.

The core multimodal workflow uses [LangGraph](https://www.langchain.com/langgraph) to orchestrate different models and experiment/game flows.

A key priority was enabling data collection across many different types of interactions while preserving the representational fidelity of each character (more on our measurement theory, fidelity metrics, and implementation details can be found in the wiki). To do this, we created a declarative graph builder: researchers define experiments or games in the games/ directory—specifying models, prompts, characters, and flow logic—and the system compiles these into executable LangGraph graphs. These orchestrate the experiment while providing measurable character fidelity, performance metrics, and a variety of data collection methods throughout the flow.

This architecture allows us to seamlessly mix models from different providers (OpenRouter, Hugging Face, local models, etc.) while enforcing a shared simulation subgraph that ensures consistency and character integrity across experiments. As a result, we can easily vary cognitive abilities, goals, and interaction structures to study phenomena like goal inference, predictive accuracy, and human responses to cognitive divergence—without needing to modify core system code.