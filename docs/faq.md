# FAQ

This page addresses some frequently asked questions about the simulation engine project. If you have additional questions or need further clarification, please feel free to reach out the [maintainers](mailto:mworkman9@gatech.edu).

## **What is *Diverse Intelligence* (DI)?**
The terms diverse cognitive systems, diverse intelligences, and diverse cognitive agents are used interchangeably throughout to refer to the full landscape of intelligent entities—those with capacity to competently navigating a space to achieve a goal. This includes humans with non-normative or shifting sensory, regulatory, perceptual, or action modalities (e.g., individuals with atypical neurophysiology, temporary disabilities, or non-standard communication methods), as well as bioengineered humans, chimeric beings, synthetic intelligences, and other non-human agents that diverge more significantly. The term is meant to be inclusive of all entities that meet the functional criteria of goal pursuit, irrespective of origin or embodiment.

## **Why don't you include more characters like from Sci-Fi, Fantasy, or other speculative fiction?**
A lot of fictional characters—especially in TV, film, and popular sci-fi/fantasy—feature dramatic differences in abilities or appearance. But despite that, their goals, motivations, and cognitive structures are often still fundamentally human-like, usually grounded in Western cultural norms. You can modify a character’s physiology or abilities in countless ways without meaningfully changing their goal-inference capacities or cognitive architecture. This type of variation doesn't capture the kinds of cognitive diversity that is most informative for our research.

The set of core characters isn’t based on every imaginable variation, but on informative variation—i.e., characters that help us study real differences in cognition, goal formation, perception, and interaction across diverse cognitive systems.

## **How do we handle adversarial inputs/gameplay?**
In truth...not well. This is not designed to be a robust production system. Its an experimental research tool so we have some checkpoints in place but assume that users/players are resarch participants that will generally follow instructions.

Its also somewhat counter productive to have strict adversarial input handling because our own concepts of "adversatial" and appropriate behavior impose anthropocentric and/or cultural norms that may exclude interesting behaviors. Instead our checkpoints focus on making sure the actions are in-character.

## **Why Scenario-Based Role Play for Simulation?**

We opted for a scenario-based, role-play simulation engine because it offers the most expressive, flexible, and scalable way to evaluate and develop intelligent agents. Specifically, 

1.	Beyond Static Q&A
Static tests like SAT-style or intelligence test questions measure performance on fixed problems. While useful, they don’t capture the dynamic, open-ended reasoning and decision-making needed for agents to handle real-world tasks or multi-turn interactions.

2.	Supports Self-Play and Creative Exploration
For agents to develop creativity, self-exploration, and learning in complex environments, they need more than multiple-choice tests. Scenario-based role play enables agents to self-play—interacting with each other or humans in open-ended ways, mirroring how humans learn through experience and improvisation.

3.	Better Evaluation via Rubrics
Open-ended simulations can be evaluated using rubric-based methods, where criteria for success are predefined and scored by humans or large language models (LLMs). Research shows that LLM and human evaluations often align closely when rubrics are clear, making the approach scalable and reliable.

4.	Closer to Human Cognitive Assessment
Scenarios and role play replicate the interactive, adaptive nature of real-world tasks, providing richer signals of competence. This aligns evaluation with how humans would naturally engage with a system, rather than relying on artificial benchmarks.

5.	Growing Research Backing
Many multi-agent frameworks today focus on physics-based simulations. However, multi-agent role-play scenarios have emerged as a powerful way to study collaboration, negotiation, and reasoning—key ingredients for advanced AI systems.

## **Why We Don’t Use Task-Specific Evaluations like GrabThatX**
Many AI evaluation tools focus on task completion—e.g., GrabThatX, where performance is judged by how well an agent executes a predefined action. We chose not to use this approach for several reasons:

1.	Task Completion ≠ Goal Understanding
These benchmarks ask, Can the agent do the thing? But our research asks a different, more foundational question:
Does the agent even understand what the other agent cares about?
Execution and reasoning are separate problems. We want to measure core reasoning ability first, before jumping to performance on specific tasks.

2.	Task-Specific Tests Are Narrow
Tools like GrabThatX are typically designed for training agents in self-play or evaluating assistant-like systems where the goal is to help humans complete a concrete task.
Our aim is broader: to evaluate reasoning across diverse cognitive agents with varied interfaces, preferences, and expressive modalities—not just agents solving one fixed problem.

3.	Rubric-Based Evaluation Scales Better
We use rubric-based evaluation to measure whether an agent correctly infers another’s goals or intentions. Research shows this approach is just as accurate as task-specific metrics while allowing us to simulate open-ended, heterogeneous scenarios rather than hardcoding one task.

4.	Foundational vs. Normative Assumptions
Many assistant bots bake in normative assumptions about “typical” cognitive agents and tasks. We step back from that—we want a system that can model and evaluate a wide variety of cognitive styles before assuming what “success” looks like in execution.

## **Why Use a Narrative/Text-Based Simulation Environment Instead of Physics Engines, Real-Time Simulations or Other Existing Simulation Engines?**
The most relevant phenomena for our research aren’t the ones rooted in physical space—they’re the ones that occur in thoughtspace. What matters for us is not necessarily an agent moves through a simulated environment, but how it represents the world, what concepts it forms, what it imagines, and how it reasons about possibilities. That’s the level at which behavior, intention, communication, and coordination emerge and are negotiated.

Language-based simulation gives us direct access to that internal space of cognition. It’s simply the most practical interface for observing and interacting with agents at the level that matters for our work: their concepts, predictions, values, and internal models—not the physics of their surroundings.

1. Efficiency and Scalability
Physical simulations—whether in real hardware or physics engines—carry high computational and integration costs. They are only as powerful as the engine’s fidelity and quickly become bottlenecks for broad experimentation.

Linguistic simulation bypasses these constraints, enabling fast, large-scale exploration of reasoning behaviors at a fraction of the cost.

2. Representational Capacity of Language
Language is a structurally complete, generative system with essentially unlimited expressive power. It can:
	•	Encode arbitrary processes beyond physical reality.
	•	Serve as a universal interface for other modalities through coarse-graining.
	•	Support open-ended reasoning across any system capable of shared meaning.

This makes it uniquely suited to representing the diversity of realities we want to simulate.


3. Future-Proof Core Reasoning
The combination of low computational cost, unbounded expressivity, and modular integrability makes a linguistic core reasoning system exceptionally versatile. Even as we add other interfaces—visual, robotic, or multimodal—a text-based reasoning core remains valuable because any system can feed into it at the right level of abstraction.


4. Alignment with State-of-the-Art AI
Finally, linguistic models are being widely adopted and arguably most powerful as AI systems. Simulating reasoning in linguistic space naturally aligns with these systems, ensuring compatibility with the strongest AI technologies available today.

This approach provides computational efficiency, expressive breadth, and a unified reasoning core—all tailored to exploring the limits and diversity of cognitive systems.

## **Address the coase-graining critique**
The coarse-graining critique points out that when you simulate in linguistic space, you assume that information from other modalities (e.g., vision, audio, sensory inputs) is being compressed or coarse-grained into language without losing critical detail. Critics argue this might ignore nuances not easily captured in words—tone, texture, or fine-grained perceptual data.

Our response is:
1.	We Explicitly Acknowledge This Limitation
Any system that translates across modalities—vision to text, audio to text—faces this. There is always potential for information loss, noise, or artifacts when coarse-graining data into a single expressive medium.

2.	It’s a Separate Problem from What We’re Studying (here)
Our simulation engine assumes that the linguistic descriptions are already sufficiently high-quality. We’re not solving the multimodal coarse-graining problem itself. Instead, we’re asking:
Given a good linguistic representation, can the agent reason correctly about it?

3.	Why This Assumption is Acceptable
In complex research problems, isolating variables can be valuable. Here, we focus on reasoning and goal inference, not on perfect multimodal fusion. Better coarse-graining methods can be plugged in later as they improve, but they don’t change the core reasoning question we’re tackling.

4.	Universal Trade-off
This is not unique to language. Any time information is transferred across representational systems, you face trade-offs between expressivity, compression, and interpretability. Our engine simply works on the assumption that linguistic representations are “good enough” for studying reasoning performance.


## **Why only unidirectional learning/evaluation?**

We deliberately designed game-play to go one way in the current version of the simulation engine, even though real-world cognitive interactions are bi-directional. 

The reasoning is:
1.	Practicality for Evaluation
This system is primarily an evaluation framework for agents engaging in self-play and self-learning. Measuring one-way goal inference lets us focus on the core reasoning ability—can one agent accurately infer what another agent cares about?—without adding complexity that doesn’t yet change the evaluation metric.

2.	Modularity for Future Extensions
We recognize that real-world interactions often involve bi-directional goal inference and even multi-agent goal negotiation. Our design is modular and extensible so that bi-directional and multi-agent goal inference could be added in the future as compute budgets and research needs justify it.

3.	Scalability Constraints
Adding bi-directional inference or multiple agents significantly increases computational demands and slows down simulation. Working in linguistic space helps keep things scalable, but one-way inference strikes the right balance for the current goals.

4.	Keeping It Simple, for Now
By isolating unidirectional goal inference, we can develop robust benchmarks first. Later, more complex setups—bi-directional or multi-agent—can be built on top without re-engineering the whole system.

## **Why the Simulation Uses Synchronous Response**
We use synchronous, turn-taking responses in the current version of the simulation engine even though real-world interactions are often asynchronous and less structured. This was a hard design decision but our justifications are:

1.	Practical for Recording and Review
Turn-taking makes it much easier to record, review, and analyze transcripts of conversations. This structure provides clean, separable interaction points, which is especially valuable in early-stage evaluation.

2.	Natural for Human Communication
Human conversation is naturally turn-based, so synchronous responses align with common interaction patterns while we focus on core reasoning evaluation.

3.	Focus on Reasoning, Not Interface Dynamics
Our priority is testing goal inference and reasoning ability across diverse agents—not solving the additional complexity of asynchronous or free-form interaction yet.

4.	Modular and Extensible Design
The simulation engine is designed so that future versions can support asynchronous or open-canvas environments where agents respond freely rather than in turns.

5.	Start Simple, Expand Later
We fully acknowledge this as a limitation and plan to remove it in future iterations. But for now, simplicity, clarity, and practicality make synchronous response the right choice.



---

### **What is our working definition of *intelligence*?**
Our working definition: **Intelligence is competency navigating a space to achieve a goal.**  
- This is **useful** because it is **empirically testable**—we can measure competency, define a space (physical, social, conceptual, computational), and assess goal achievement.  
- It is **domain-agnostic**, applying to humans, non-human animals, AI, and other possible minds.  
- It allows for meaningful **comparisons across diverse intelligence forms** without relying on human-centric benchmarks.

---

### **What do you mean by the *space of possible minds*?**
The *space of possible minds* is a conceptual domain encompassing all potential types of cognitive systems—including those unlike anything we currently know—across species, embodiments, and substrates.  

It invites us to imagine minds built not only from neurons and silicon, but from **unconventional computing systems**:  
- Biological substrates (slime mould, plant signaling networks)  
- Chemical computing  
- Photonic or quantum systems  
- Hybrid bio-digital organisms  

Exploring the space of possible minds often overlaps with **unconventional computing** research, which studies computation beyond traditional digital architectures. Andrew Adamatzky’s *[Unconventional Computing Handbook](https://www.routledge.com/Unconventional-Computing-Handbook/Adamatzky/p/book/9780367573083)* surveys such approaches, many of which could underpin radically different forms of cognition.

---

### **What is the *interface problem*?**
At its core, the interface problem is about **interfacing between difference**—minimizing overhead when interacting across cognitive systems with various sensory, perceptual, regulatory, and action modalities.

Without solving it:
- We **cannot build a truly integratable society**—one where cognitive divergence is supported rather than flattened.
- Without tailored mediation, those whose ways of thinking, perceiving, and acting differ significantly remain **excluded or exhausted** in social, digital, and physical systems]

To address this, we need systems that:
1. **Deeply understand** a being’s sensory–perception–regulation–action profile over time.
2. **Translate** between these modalities to enable mutual understanding.
3. **Construct tailored interfaces** that support communication, contribution, and belonging.

Societies that solve the interface problem **do not impose sameness**, but reduce interaction friction so that difference becomes a meaningful, sustainable asset—not a barrier.

### **Why is *goal inference* the metric of choice? What does understanding another cognitive agent’s goal-space matter?**
Many of our simulations and games revolve around the player inferring a character’s goals—either the specific goal it’s pursuing or the upper bounds of what it’s capable of imagining as a goal. We use this as a proxy for understanding.

The reason is simple: goals are a practical, experimentally useful model for predicting behavior. When we say “goals,” “values,” or similar terms, we’re not claiming those are the true inner workings of an agent. These are just modeling tools—ways of compressing behavior into something we can reason about and test against.

If a better model comes along, we’ll use it. But right now, goal-based models are simple, flexible, and tend to generalize across a wide variety of systems—from basic homeostatic processes to single agents to complex collective intelligences. They give us a common language for making predictions about what an agent is likely to do next.

So goal inference isn’t about declaring that goals are the essence of cognition. It’s about utility: goals give us a workable handle on understanding and interacting with diverse cognitive systems.

---

# **Additional Resources**
- **AI Could Be a Bridge Toward Diverse Intelligence** — Michael Levin explores how AI can push us to redefine intelligence and humanity  
  [noemamag.com](https://www.noemamag.com/ai-could-be-a-bridge-toward-diverse-intelligence)  
- **Biology, Buddhism, and AI: Care as the Driver of Intelligence** — Doctor *et al.* proposes that redefining intelligence as a relational, embodied process driven by care—attention, empathy, and responsiveness—integrating insights from biology and Buddhism to better understand and design diverse intelligences. [mdpi.com](https://www.mdpi.com/1099-4300/24/5/710)  
- **The Space of Possible Minds** — Explores the continuum of intelligence, from cells to complex minds, and urges broader ethical frameworks  
  [edge.org](https://www.edge.org/conversation/murray_shanahan-the-space-of-possible-minds)  
- [**Rethinking Accessibility in the Age of Cognitive Pluralism** (on interface friction and divergence)](https://fuzzy-tribble.github.io/whoami/25-06%20Rethinking%20Accessibility%20in%20the%20Age%20of%20Cognitive%20Pluralism.html)
