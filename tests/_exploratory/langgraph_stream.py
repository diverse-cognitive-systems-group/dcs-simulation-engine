from langgraph.graph import END, StateGraph


# --- 1. Simple state type ---
class State(dict):
    pass


# --- 2. Nodes ---
def step_one(state: State):
    # Real state update, not a branch / command
    return {"step_one_result": "Hello"}


def step_two(state: State):
    # This will now work because step_one_result exists
    return {"final": state["step_one_result"] + " world!"}


# --- 3. Build graph ---
graph = StateGraph(State)
graph.add_node("step_one", step_one)
graph.add_node("step_two", step_two)

graph.set_entry_point("step_one")
graph.add_edge("step_one", "step_two")
graph.add_edge("step_two", END)

compiled = graph.compile()

# Optional: visualize
print(compiled.get_graph().draw_ascii())

# --- 4. Synchronous streaming ---
for event in compiled.stream({"input": "test"}):
    print("EVENT:", event)

print("\nFinal result:")
print(compiled.invoke({"input": "test"}))
