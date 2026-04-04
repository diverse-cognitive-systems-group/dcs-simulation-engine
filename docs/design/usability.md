Ensuring that DCS-SE us easy to use is a core design principle. Usability is a foundational study that evaluates this and is re-run when user-facing changes are made. It is intended to identify and reduce usability-related confounds prior to downstream experimental use of DCS-SE.

The complete study design, including research questions, methods, and results, is documented below and results for all release versions are linked in the results section.

---

# DCS-SE Usability Study

## Purpose and Contribution 

Evaluate the usability, clarity, and practical value of DCS-SE for both human players and users, with the goal of identifying and reducing usability-related confounds prior to downstream experimental use. This study serves as the first formal usability evaluation of DCS-SE, a newly developed research platform, and is intended to inform iterative refinement.  

DCS-SE was developed to support controlled experimentation with interactive agents with diverse abilities in ways not supported by existing platforms, necessitating a dedicated usability evaluation prior to experimental deployment. 

## Research Questions 

Are there usability or comprehension issues in DCS-SE that could introduce unintended barriers or confounds for human players using the graphical user interface, within the accessibility affordances currently supported by the system? 

Are there usability, workflow, or documentation issues in DCS-SE that could impede researchers’ ability to design, deploy, or manage experiments as intended? 

Do identified usability issues vary by user role (player vs. researcher), experience level, or game context? 

## Study Design 

This is a formative mixed-methods usability study combining qualitative and limited quantitative data. The study uses purposive sampling, real users from the target populations, and realistic goal-directed tasks. To minimize artificiality, participants interact with DCS-SE in naturalistic settings using the same interface, documentation, and prompts provided to actual users. 

Data are collected in small, iterative rounds. Findings from each round may inform system refinements before subsequent rounds. To preserve interpretability, usability issues identified prior to system changes are documented and analytically distinguished from issues observed after refinements. Cross-round comparisons focus on the presence or absence of recurring usability themes rather than on direct performance metrics. 

Data collection continues until thematic saturation is reached, defined as the point at which no substantively new usability issues are identified across two consecutive rounds within a given study component. 

Participants may complete multiple study components and sessions. Repeat participation and role changes (e.g., player to researcher) are explicitly documented. Data from participants with prior exposure to DCS-SE are analyzed separately or used for contextual interpretation rather than for cross-participant comparisons. 

Members of the DCS research team may participate. Their participation is explicitly labeled, and their data are used to identify potential usability issues but are not used as primary evidence for claims about novice or external users. 

At the time of this study, DCS-SE’s graphical interface does not include dedicated accessibility features such as screen reader support or alternative input modalities; usability findings should therefore be interpreted within the scope of these interface constraints. 

### Ethics and Oversight 

This study falls under Institutional Review Board (IRB) approval number IRB2025-1006 which covers interviews, follow-up discussions, collection of gameplay data, and general user feedback. The approved protocol excludes vulnerable populations and governs all recruitment, consent, and data collection procedures used in this study. 

## Participants and Sampling 

Participants are recruited from multiple sources, including academic networks, campus populations, and researcher social networks. All participants provide informed consent using a single standardized Research Participation Consent Form that describes the range of possible study activities. 

Following an optional preliminary discussion, participants are purposively assigned to study components most likely to yield informative usability feedback based on their background, experience, and anticipated use of DCS-SE. 

## Procedure 

Participants complete assigned usability tasks independently in naturalistic settings, using the same instructions and prompts provided to actual DCS-SE player users. No additional training or guidance is provided beyond existing documentation. Researchers do not intervene during task completion beyond responding to technical failures unrelated to usability. 

After task completion, participants provide feedback via asynchronous written responses or a scheduled follow-up discussion. Qualitative data are collected through written responses and optional semi-structured interviews. System and gameplay logs may also be analyzed as supplementary data to examine interaction patterns, system behavior, and narrative or story consistency. 

## Study Component A: Usability for Human Players

### Objective 

Evaluate the usability and clarity of the DCS-SE graphical user interface for human players. 

### Interface Context 

DCS-SE uses a standard, off-the-shelf graphical interface that was developed and refined with input from HCI-trained graduate students prior to this study. Given the simplicity and standardized nature of the interface, this component is intended as verification-focused usability testing aimed at identifying any remaining usability barriers, and therefore uses a small minimum sample size (approximately three participants per round). If qualitative analysis shows that themes are not recurring across participants, the sample size will be increased. 

### Participants and Sampling 

Human players are purposively sampled to capture variation in technological familiarity, using age range and gameplay experience as proxies for technological familiarity. 

### Tasks 

Participants are given one or more assignments which consist of playing a game and a character. 

### Data Collection 

Participants receive the following standardized prompt: 

Thank you for taking the time to help us evaluate the usability of our simulator!  

It simulates beings with diverse abilities, and we need some player input to understand if the interface is clear and easy to use. 

<game_play_link> 

The game play link takes them to a pre-play consent form that includes a question about their technical expertise. 

In game feedback and game play logs like time between turns, commands and help menus used, etc. is logged. 

Then after each assignment, a post-play form collects data on any usability related issues. 

### Data Analysis 

Analysis focuses on identifying recurrent usability issues evidenced by breakdowns, confusion, or workarounds. Reported preferences or aesthetic judgments are noted but analytically distinguished from usability problems unless they demonstrably affect task completion or interaction flow. Comparisons are made across levels of technological familiarity to identify differential user barriers. 

## Study Component B: Usability for General Users

### Objective 

Evaluate the usability, clarity, and perceived research value of DCS-SE for researchers designing, deploying, and managing experiments as well as for non-researchers other practitioners that host games for learning or training purposes. 

### Participants and Sampling 

Participants are purposively sampled to represent researchers and practitioners with a range of disciplinary backgrounds and levels of technical expertise, including AI, data science, cognitive science, psychology, and related humanities fields. 

### Tasks 

Participants follow the DCS-SE User Guide to complete realistic end-to-end research workflows, including: 

Running and deploying existing games 

Creating, adding, and testing new characters 

Creating, adding, testing, and deploying new games for human and AI players 

Collecting experimental data for analysis 

### Data Collection 

Participants receive the following standardized prompt: 

Thank you for participating in our usability study. 

DCS-SE is a tool designed to support research on engagement between agents with diverse forms, functions, and abilities. We are interested in understanding how clear, usable, and effective the system is for researchers from different backgrounds. 

 

Please (complete 1, 2, 3, or 4 above) 

 

Then, please reply with dates and times you are available for a follow-up discussion to share your feedback. This discussion will focus on: 

Which components of DCS-SE you interacted with and for how long 

The study or experiment you designed, ran, or deployed, and the time required 

Which parts of the workflow were intuitive, difficult, clear, or confusing 

Whether and how you see DCS-SE as useful for your research 

 

Please click the link below and follow the instructions in the User Guide to begin: 

<link> 

 

Feedback is collected through follow-up discussions and, when needed, asynchronous written responses. Because the researcher workflow is more involved, discussions are preferred, as they allow for deeper understanding and avoid lengthy forms that would likely require additional clarification. System configuration data and logs may also be reviewed to help contextualize reported workflow challenges and design decisions. Follow-up discussions focus on concrete actions taken, breakdowns encountered, and workarounds used. Hypothetical or speculative evaluations are noted but are not central to analysis. 

### Data Analysis 

Analysis emphasizes workflow breakdowns, points of confusion, and inefficiencies that impede task completion. Expressions of perceived research value are interpreted as subjective assessments and are not treated as evidence of system effectiveness. 

## Limitations 

### Sampling and Participant Bias 

This study is a formative usability evaluation intended to identify and reduce usability-related confounds prior to downstream experimental use of DCS-SE. Findings are qualitative, exploratory, and not intended to support statistical generalization. Participant samples are purposively selected and relatively small, consistent with usability research, and include individuals recruited through academic and researcher networks. Some participants may have prior familiarity with DCS-SE, including members of the research team. Although such participation is disclosed and analytically distinguished, insider familiarity may influence the types of issues identified. 

### Accessibility Scope 

Usability findings reflect interaction with the current implementation of DCS-SE and its existing documentation and interface affordances. At the time of this study, the graphical interface does not include dedicated accessibility features such as screen reader compatibility or alternative input modalities; conclusions should therefore be interpreted within this scope. 

### Iterative Design Effects 

Data are collected in iterative rounds, and refinements may be introduced between rounds to address identified usability issues. While this supports system improvement, it limits direct comparison across rounds and constrains longitudinal interpretation of specific usability findings. 

Finally, iterative refinements may occur between data collection rounds. While this supports usability improvement, it limits direct comparison across rounds and constrains longitudinal interpretation of specific usability issues. 

## Results

Results for the latest engine are linked here: [DCS-SE Usability Study Results](../reports/usability_report.html)

 