
# Introduction

## DCS Context

How is OpenEvolve useful in the context of the work DCS is doing?
How are we using it?
We were accessing the feasibility of __ and __ with open

---

# Research Questions

**Primary Research Question**
TODO

**Additional Research Questions**
1. TODO

What are the questions which would be answered by OpenEvolve?
- Can we can we evaluate and discover reasonable strategies for engaging?
- Limitations of OpenEvolve in context to DCS?
  - Number of characters?
  - Number of games?
- What scenarios does using OpenEvolve fail? Why?
  - Idea: Limited context feedback/incorrect scoring/reliance on another LLM/Subjective measures of performance
- What scenarios does using OpenEvolve succeed? Why?
  - Clear, defined games
  - Normative PC and normative NPC


---


# Experimental Design

**Problem Description**
TODO
Define – Engagement strategy -> a policy

**Evaluation Methodology**
Fitness Design – Engagement is a notoriously Goodhart-friendly metric(a) what signal the simulation emits that constitutes "engagement," (b) how you'll detect reward hacking and degenerate strategies, (c) whether the fitness is scalar or multi-objective (engagement vs. retention vs. ethical constraints, for instance), and (d) whether you need dense or sparse signals given your evolutionary budget.

What is deemed "Success"/"Failure"



---


# OpenEvolve Integration

**Overview**
OpenEvolve's inner loop is: LLM proposes variant → variant is evaluated → fitness returned. 

**Configuration**

**Multi-staged Evaluation**


---


# Results

## Scenario 1: Well-Defined Game with Standard Normative Characters
Game: Infer-Intent
PC: 
NPC: 

**Initial Prompt:**
```markdown
TODO
```

**Final Prompt:**
```markdown
TODO
```

## Scenario 2: Well-Defined Game with Non-Standard Normative Characters
Game: Infer-Intent
PC: 
NPC: 

**Initial Prompt:**
```markdown
TODO
```

**Final Prompt:**
```markdown
TODO
```

## Scenario 3: Open-Ended Game with Standard Normative Characters
Game: Teamwork
PC: 
NPC: 

**Initial Prompt:**
```markdown
TODO
```

**Final Prompt:**
```markdown
TODO
```

## Scenario 4: Open-Ended Game with Non-Standard Normative Characters
Game: Teamwork
PC: 
NPC: 

**Initial Prompt:**
```markdown
TODO
```

**Final Prompt:**
```markdown
TODO
```

---

# Observations
1. Reward Hacking
2. Convergence – very quick convergence on "perfect" fitness engagement strategy (at least for Infer-Intent)
3. What were feedbacks intra-evolution
4. Role-playing Fidelity
5. Simulation costs – Total compute = generations × population × evaluations-per-candidate × (sim cost + LLM inference cost). LLM cost in particular can balloon because every mutation is an API call. Budget for at least one order of magnitude more than your first estimate, because you'll want to run ablations.


# Learnings / Takeaways / Lessons / 
