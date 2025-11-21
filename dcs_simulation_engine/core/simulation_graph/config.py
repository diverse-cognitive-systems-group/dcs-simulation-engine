"""Graph models for simulation engine configuration."""

from __future__ import annotations

import inspect
from typing import Any, Dict, List, Optional, Type, Union

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    create_model,
    field_validator,
    model_validator,
)

from dcs_simulation_engine.core.simulation_graph import builtins
from dcs_simulation_engine.utils.serde import SerdeMixin


class Node(BaseModel):
    """Node in the simulation graph.

    With kind-specific validation:
    - custom:
        provider, model, system_template (required)
        config must be empty
    - builtin.<name>:
        builtin must exist; config validated if spec provided
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    kind: str  # "custom" | f"builtin.{name}"

    # Builtins carry their additional arguments in `kwargs`
    kwargs: Dict[str, Any] = Field(default_factory=dict)

    # Custom-only fields (top-level, NOT in kwargs)
    provider: Optional[str] = None
    model: Optional[str] = None
    system_template: Optional[str] = None
    additional_kwargs: Optional[Dict[str, Any]] = None

    @model_validator(mode="before")
    @classmethod
    def _default_kwargs_for_builtin(cls, data: Any) -> Any:
        """Ensure 'kwargs' key exists for built-in kinds, defaulting to {}."""
        if isinstance(data, dict):
            k = data.get("kind")
            if isinstance(k, str) and k.startswith("builtin."):
                if data.get("kwargs") is None or "kwargs" not in data:
                    data = {**data, "kwargs": {}}
        return data

    # Optional: normalize None -> {} universally (harmless for customs)
    @field_validator("kwargs", mode="before")
    @classmethod
    def _none_to_empty_dict(cls, v: Any) -> Any:
        """Convert None kwargs to empty dict."""
        return {} if v is None else v

    @model_validator(mode="after")
    def _validate_kind_specifics(self) -> "Node":
        if self.kind == "custom":
            missing = [
                k
                for k in ("provider", "model", "system_template")
                if not getattr(self, k)
            ]
            if missing:
                raise ValueError(
                    f"custom node '{self.name}' missing: {', '.join(missing)}"
                )
            if self.kwargs:
                raise ValueError(
                    f"custom node '{self.name}' must not define 'kwargs'; "
                    "put inputs at the top level (provider/model/system_template)."
                )
            return self

        if self.kind.startswith("builtin."):
            builtin_name = self.kind.split(".", 1)[1]
            self._ensure_builtin_exists_and_validate_kwargs(builtin_name)
            return self

        raise ValueError(
            f"Unsupported kind '{self.kind}' for node '{self.name}'. "
            "Use 'custom' or 'builtin.<name>'."
        )

    def _ensure_builtin_exists_and_validate_kwargs(self, builtin_name: str) -> None:
        """Validate builtin existence and that `kwargs` matches its signature.

        - `config` is a kwargs dict for the builtin function.
        - Required params (no default) must be present.
        - Optional params (with defaults) need not be provided.
        - Types are checked using the function's annotations.
        - Extra keys are forbidden unless the function accepts **kwargs.
        """
        # 1) function exists & callable
        try:
            func = getattr(builtins, builtin_name)
        except AttributeError as e:
            raise ValueError(
                f"builtin '{builtin_name}' not found in builtins.py"
            ) from e
        if not callable(func):
            raise ValueError(f"builtin '{builtin_name}' exists but is not callable")

        # If a strict Pydantic config model is registered, use it
        cfg_models: Optional[Dict[str, Type[BaseModel]]] = getattr(
            builtins, "CONFIG_MODELS", None
        )
        if isinstance(cfg_models, dict) and builtin_name in cfg_models:
            Model = cfg_models[builtin_name]
            try:
                # TODO: this will fail if something like {{ EXIT }} is
                # used in config values...consider skipping or validating differently
                # if {{ and }} are detected?
                Model(**self.kwargs)
            except ValidationError as ve:
                raise ValueError(
                    f"Invalid kwargs for builtin '{builtin_name}' \
                        in node '{self.name}': {ve}"
                ) from ve
            return

        sig = inspect.signature(func)
        params = sig.parameters

        # keys the engine injects automatically (not required in config)
        injected = {"state", "context", "logger"}

        # detect **kwargs and reject *args (config is kwargs only)
        accepts_kwargs = any(
            p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()
        )
        if any(p.kind == inspect.Parameter.VAR_POSITIONAL for p in params.values()):
            raise ValueError(
                f"builtin '{builtin_name}' uses *args which is \
                    not supported by config kwargs"
            )

        # Build a dynamic Pydantic model from the function parameters
        fields: Dict[str, tuple[type, object]] = {}
        for name, p in params.items():
            if name in injected:
                continue
            if p.kind not in (
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                inspect.Parameter.KEYWORD_ONLY,
            ):
                # POSITIONAL_ONLY can't be provided via kwargs
                raise ValueError(
                    f"builtin '{builtin_name}' parameter '{name}' is \
                        positional-only; use keyword-capable params."
                )
            anno = p.annotation if p.annotation is not inspect._empty else Any
            if p.default is inspect._empty:
                fields[name] = (anno, ...)  # required
            else:
                fields[name] = (anno, p.default)  # optional with default

        DynamicModel = create_model(  # type: ignore[misc]
            f"BuiltinConfig__{builtin_name}",
            __base__=BaseModel,
            **fields,  # type: ignore
        )
        # Control extras based on **kwargs presence
        DynamicModel.model_config["extra"] = "allow" if accepts_kwargs else "forbid"  # type: ignore[index]

        # Now validate the provided kwargs (empty dict is fine if all params
        # have defaults)
        try:
            DynamicModel(**(self.kwargs or {}))
        except ValidationError as ve:
            raise ValueError(
                f"Invalid kwargs for builtin '{builtin_name}' in node '{self.name}':"
                f" {ve}"
            ) from ve


class IfThen(BaseModel):
    """Conditional edge item with 'if' and 'then'."""

    model_config = ConfigDict(populate_by_name=True)
    if_: str = Field(alias="if")
    then: str


class ElseOnly(BaseModel):
    """Conditional edge item with only 'else'."""

    else_: str = Field(alias="else")


ConditionalItem = Union[IfThen, ElseOnly]


class ConditionalTo(BaseModel):
    """Conditional 'to' field for edges."""

    conditional: List[ConditionalItem] = Field(default_factory=list)


class Edge(BaseModel):
    """An edge in the simulation graph, representing message flow between nodes."""

    from_: str = Field(alias="from")
    to: Union[str, ConditionalTo]


class GraphConfig(SerdeMixin, BaseModel):
    """Configuration for the entire simulation graph."""

    name: Optional[str] = Field(default="graph-config")
    description: Optional[str] = Field(default=None)
    # State overrides
    # TODO: if supplied make sure they conform to expected SimulationGraphState schema
    state_overrides: Dict[str, Any] = Field(default_factory=dict)
    nodes: List[Node] = Field(default_factory=list)
    edges: List[Edge] = Field(default_factory=list)

    @model_validator(mode="after")
    def fill_defaults(self) -> "GraphConfig":
        """Fill in default values for name and description if not provided."""
        if self.description is None:
            self.description = (
                f"A simulation graph with {len(self.nodes)} nodes "
                f"and {len(self.edges)} edges."
            )
        return self

    def list_nodes(self) -> List[str]:
        """List node names present in the config (empty list if None)."""
        return [n.name for n in self.nodes]

    def get_node_config(self, node_name: str) -> Optional[dict[str, Any]]:
        """Return the raw config dict for a given node name, if present."""
        from loguru import logger

        for node in self.nodes:
            if node.name == node_name:
                return node.model_dump()
        logger.warning("Node config not found for name: {}", node_name)
        return None

    def get_system_prompt(self, agent_name: str) -> Optional[str]:
        """Return the unrendered system prompt template for a given agent/node."""
        cfg = self.get_node_config(agent_name)
        if not cfg:
            return None
        return cfg.get("system_prompt_template")
