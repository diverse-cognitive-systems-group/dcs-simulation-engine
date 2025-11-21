import asyncio


async def run_graph(graph, input_state, config):
    return await graph.ainvoke(input_state, config=config)


async def main():
    task = asyncio.create_task(
        run_graph(graph, {"msg": "long job", "result": None}, config)
    )

    # later, user hits Cancel:
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        print("Graph call cancelled")


asyncio.run(main())
