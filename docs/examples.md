👉 See the [`/examples/run_configs/`](..) folder for all example run configurations.

## Education & Training

DCS-SE supports training and education by enabling human players to engage with a wide range of cognitive profiles, including neurodivergent individuals and those with differing sensory, perceptual, and regulatory modalities.

Because these populations are often underrepresented in everyday interactions, many professionals—such as clinicians, educators, managers, and caregivers—have limited opportunities to build fluency in communicating across cognitive differences.

DCS-SE's [core characters](../design/characters.md) are grounded in real-world cognitive diversity, created with and evaluated by individuals with divergent profiles. This allows users to practice, observe, and refine interactions in a controlled environment, leading to more inclusive, adaptive, and effective approaches across domains.

### Example: Inclusive Workplace Training

In this example, users run `/examples/run_configs/training.yml`. It specifies that the engine should run the Teamwork game with neurotypical player characters and neurodivergent non-player characters. It also includes a basic intake form collecting training participation consent and the Teamwork game by default evaluates how well players work with non-player characters to accomplish a shared goal.

After gameplay, managers or facilitators can review participant results and feedback, such as:

- What participants learned
- What they found challenging
- Whether and how their understanding of neurodivergent individuals changed

This supports both iterative improvement of training programs and measurement of training impact.

## General Research

DCS-SE supports a wide range of research across disciplines—including psychology, neuroscience, biology, and speculative domains such as exobiology—through its diverse character set and configurable simulation environments.

By providing a controlled and repeatable system for simulating varied cognitive architectures, the engine enables researchers to design experiments, test hypotheses, and observe interactions that may be difficult or impossible to study directly. This includes variation in perception, decision-making, communication, and behavior across both human and non-human agents.

Because configurations are parameterized and reproducible, DCS-SE is well-suited for:

- Comparative studies across cognitive profiles
- Exploratory research into unfamiliar systems
- Scenario-based testing under controlled conditions

### Example: Psychology Research on Understanding Diversity

A psychology researcher might investigate how individuals adapt to increasingly divergent cognitive profiles. 

Example research question:

- How does understanding change as sensory, perceptual, and regulatory modalities diverge?

In this example, users run `/examples/run_configs/benchmark-humans.yml`, which specifies a progressive divergence configuration. This means that the engine will simulate interactions with characters that become increasingly divergent across runs, allowing researchers to observe how understanding evolves as cognitive differences increase.

### Example: Social Science Research on Learning Across Cognitive Differences

Researchers can also study how quickly different populations learn to effectively engage with a specific cognitive profile.

Example research questions:

- How long does it take different demographic groups to learn to interact effectively with a given cognitive profile?
- Do some populations adapt faster, develop better mental models, or demonstrate greater tolerance in interaction?
- How does performance improve over repeated interactions with the same individual?

Example setup:

- All participants interact with the same NPC across multiple sessions or scenarios
- The NPC’s cognitive profile remains fixed
- Performance is tracked over time (e.g., communication success, task completion, alignment)

This allows researchers to measure:

- Learning rate (speed of improvement across sessions)
- Adaptation strategies (how participants change behavior)
- Generalization (whether learning transfers to similar profiles)

By comparing these metrics across populations, researchers can identify which groups adapt more quickly or effectively to specific forms of cognitive difference.

### Example: Exobiology Research on Alien Cognition

DCS-SE can also be used to explore interactions with hypothetical or non-human cognitive systems.

Example research questions:

- How do humans attempt to communicate with fundamentally non-human cognition?
- What interaction strategies emerge when shared assumptions (e.g., perception, goals, or logic) are absent?

Researchers can define entirely novel cognitive architectures—e.g., agents with non-linear perception, unfamiliar reward systems, or non-human communication modalities—and observe how players adapt.

## AI Practitioners

DCS-SE provides a flexible environment for training and evaluating AI systems in interactions with diverse cognitive profiles. It includes a run harness capable of executing models from supported providers (e.g., OpenRouter), enabling standardized experimentation across architectures.

A major gap in current AI development is the lack of training and evaluation on cognitively diverse populations—such as neurodivergent individuals or users with non-normative communication styles. Most systems are implicitly optimized for dominant interaction patterns, limiting robustness and inclusivity.

DCS-SE addresses this by exposing models to a broader range of cognitive and communicative modalities, enabling evaluation beyond conventional benchmarks.

The platform supports both:

- Static models (fixed behavior)
- Open-ended systems (adaptive, learning agents)

### Example: Training Open-Ended AI Systems

An open-ended agent can be deployed in an exploratory simulation environment, interacting with diverse characters and learning through iteration and feedback.

Researchers may:
- Constrain environments to specific populations (e.g., divergent human profiles) for targeted learning
- Leave environments open to evaluate generalization across unfamiliar cognitive systems

This setup supports the emergence of adaptive strategies, goal formation, and context-sensitive behavior.

### Example: Benchmarking Static AI Systems

Static models can be evaluated across standardized scenarios to measure performance in interacting with diverse cognitive profiles.

Example evaluation dimensions:

- Communication clarity across modalities
- Adaptability to unfamiliar behaviors
- Robustness to ambiguity or misalignment
- Inclusivity of interaction strategies

Using fixed configurations (e.g., /examples/run_configs/benchmark-ai.yml), practitioners can compare models across identical conditions, enabling reproducible benchmarking.