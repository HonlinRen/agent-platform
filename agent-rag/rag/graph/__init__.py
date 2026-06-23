"""LangGraph 编排层对外入口。

- ``AgentState``：图内共享状态（节点读写、条件边决策）
- ``build_graph``：编译 StateGraph（router → retrieve/agent/web 等多路径）
- ``stream_graph_response``：执行图并将 LangGraph 流式事件转为 SSE 事件字典
"""

from rag.graph.builder import build_graph
from rag.graph.state import AgentState
from rag.graph.streaming import astream_graph_response, stream_graph_response

__all__ = ["AgentState", "build_graph", "stream_graph_response", "astream_graph_response"]
