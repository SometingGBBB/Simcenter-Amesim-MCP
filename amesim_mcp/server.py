"""MCP Server for Siemens Simcenter Amesim system-level simulation."""

import json

from mcp.server.fastmcp import FastMCP

from . import amesim_api as _api

mcp = FastMCP(
    "Simcenter Amesim",
    instructions=(
        "MCP server for building and running Simcenter Amesim circuits via the Circuit API. "
        "Typical workflow: connect → create_circuit → add_component → change_submodel → "
        "connect_two_ports → set_parameter_value → generate_code → run_simulation → "
        "get_variable_values → save_circuit. "
        "Positions are (x, y) integer sketch coordinates, ports are 0-based indices "
        "(port index = port number shown in the GUI, minus 1). "
        "If a named tool raises AttributeError or you need a function with no dedicated tool "
        "(e.g. AMEAddGlobalParameter, AMEGetCompilers, Design Exploration/Study APIs), use "
        "execute_python — it has ame_apy and amesim pre-imported, and you can call "
        "execute_python(\"help(ame_apy.SOME_FUNCTION)\") or "
        "execute_python(\"print([n for n in dir(ame_apy) if 'Save' in n])\") to discover the "
        "exact, version-correct signature live from the installed Amesim, exactly as the "
        "official docs recommend. "
        "AMEInitAPI checks out one Amesim license token for the whole session — call disconnect() "
        "when done so it doesn't block the user's own interactive Amesim usage."
    ),
)

ame = _api.AmesimConnection()


# ---------- Power tools ----------

@mcp.tool()
def execute_python(code: str) -> str:
    """Execute Python code in the live Amesim worker process (persistent namespace).

    Pre-bound (in the remote namespace, persists between calls):
      ame_apy — the Circuit API module      amesim — the Simulation Scripting module
    Use this for anything with no dedicated tool, or to discover a function's exact
    signature with help(ame_apy.SOME_FUNCTION) before calling it.
    Returns captured stdout (print your results!) or a traceback on error.
    """
    if not ame.is_connected():
        ame.connect()
    return ame.execute_python(code)


# ---------- Connection ----------

@mcp.tool()
def connect(version: str = "2021.1") -> str:
    """Connect to Simcenter Amesim. Starts a background worker process if none is running.
    Each worker serves exactly one session — calling connect() again while already
    connected is a no-op; call disconnect() first to switch versions or restart.

    Args:
        version: Installed Amesim version to use — "2021.1" (default) or "2404".
    """
    if ame.is_connected():
        return "Already connected. Call disconnect() first if you need to restart or switch versions."
    return ame.connect(version=version)


@mcp.tool()
def disconnect() -> str:
    """Release the Amesim license token and stop the background worker process."""
    return ame.disconnect()


@mcp.tool()
def status() -> str:
    """Check connection status and the Circuit API version."""
    if not ame.is_connected():
        return "Not connected to Simcenter Amesim. Call connect() first."
    try:
        version = ame.api.AMEGetAPIVersion()
        return f"Connected (Amesim {ame._version}, port {ame._port}). Circuit API version: {version}"
    except Exception as e:
        return f"Connected, but failed to query API version: {e}"


# ---------- Circuit lifecycle ----------

@mcp.tool()
def create_circuit(name: str) -> str:
    """Create a new, empty Amesim circuit (.ame file) and make it active.

    Args:
        name: Name for the new circuit (no extension), e.g. "FlatTwin".
    """
    ame.api.AMECreateCircuit(name)
    return f"Created circuit '{name}'."


@mcp.tool()
def open_ame_file(path: str) -> str:
    """Open an existing .ame circuit file and make it active.

    Args:
        path: Path to the .ame file (absolute, or relative to the worker's working directory).
    """
    ame.api.AMEOpenAmeFile(path)
    return f"Opened '{path}'."


@mcp.tool()
def save_circuit() -> str:
    """Save the active circuit."""
    ame.api.AMESaveCircuit()
    return "Circuit saved."


@mcp.tool()
def close_circuit(save: bool = True) -> str:
    """Close the active circuit.

    Args:
        save: Save before closing (default True).
    """
    ame.api.AMECloseCircuit(save)
    return f"Circuit closed (save={save})."


# ---------- Building / editing ----------

@mcp.tool()
def add_component(icon_name: str, alias: str, x: int = 0, y: int = 0) -> str:
    """Add a component to the sketch of the active circuit.

    Args:
        icon_name: Library icon name, e.g. "mass_friction1port", "springdamper01".
        alias: Unique name for the component within the circuit.
        x: Top-left X position in the sketch (pixels).
        y: Top-left Y position in the sketch (pixels).
    """
    ame.api.AMEAddComponent(icon_name, alias, (x, y))
    return f"Added component '{icon_name}' as '{alias}' at ({x}, {y})."


@mcp.tool()
def move_component(alias: str, x: int, y: int) -> str:
    """Move a component to a new position. Connected lines are not moved with it.

    Args:
        alias: Alias path of the component.
        x: New top-left X position (pixels).
        y: New top-left Y position (pixels).
    """
    ame.api.AMEMoveComponent(alias, (x, y))
    return f"Moved '{alias}' to ({x}, {y})."


@mcp.tool()
def rotate_component(alias: str, quarter_turns: int = 1) -> str:
    """Rotate a component's icon by -90 degrees, one or more times.

    Args:
        alias: Alias path of the component.
        quarter_turns: Number of -90 degree rotations (default 1). Negative values rotate +90.
    """
    ame.api.AMERotateComponent(alias, quarter_turns)
    return f"Rotated '{alias}' by {quarter_turns} x -90 degrees."


@mcp.tool()
def flip_component(alias: str) -> str:
    """Flip a component (mirror it) in the sketch.

    Args:
        alias: Alias path of the component.
    """
    ame.api.AMEFlipComponent(alias)
    return f"Flipped '{alias}'."


@mcp.tool()
def remove_component(alias: str) -> str:
    """Remove a component from the active circuit.

    Args:
        alias: Alias path of the component to remove.
    """
    ame.api.AMERemoveComponent(alias)
    return f"Removed component '{alias}'."


@mcp.tool()
def connect_two_ports(alias1: str, port1: int, alias2: str, port2: int) -> str:
    """Connect a port of one component/line to a port of another with a line.

    Args:
        alias1: Alias path of the first component.
        port1: Port index (0-based) on the first component.
        alias2: Alias path of the second component.
        port2: Port index (0-based) on the second component.
    """
    result = ame.api.AMEConnectTwoPorts(alias1, port1, alias2, port2)
    return f"Connected {alias1}[{port1}] -- {alias2}[{port2}] (line: {result})."


@mcp.tool()
def remove_line(alias: str) -> str:
    """Remove a connection line from the active circuit.

    Args:
        alias: Alias path of the line to remove.
    """
    ame.api.AMERemoveLine(alias)
    return f"Removed line '{alias}'."


@mcp.tool()
def create_supercomponent(
    component_aliases: str,
    submodel_name: str,
    sc_alias: str,
    sc_icon_name: str,
    gp_action: str = "duplicate",
) -> str:
    """Group components into a supercomponent (a reusable sub-circuit block).

    Args:
        component_aliases: Comma-separated alias paths of the components to group.
        submodel_name: Name for the supercomponent's generated submodel.
        sc_alias: Alias for the supercomponent instance.
        sc_icon_name: Icon name/title shown on the supercomponent.
        gp_action: How to handle global parameters referenced inside — "duplicate" (default,
                   become supercomponent-level params), "keep" (keep references), or
                   "replace" (bake in current values).
    """
    aliases = tuple(a.strip() for a in component_aliases.split(","))
    ame.api.AMECreateSupercomponent(aliases, submodel_name, sc_alias, sc_icon_name, gp_action)
    return f"Created supercomponent '{sc_alias}' from {aliases}."


# ---------- Submodels ----------

@mcp.tool()
def change_submodel(alias: str, submodel_name: str, submodel_path: str = "") -> str:
    """Assign a submodel to a component or line.

    Args:
        alias: Alias path of the component or line.
        submodel_name: Submodel name, e.g. "MAS003", "SD0000A".
        submodel_path: Directory the submodel resides in, e.g. "$AME/libmec/submodels".
                       Required the first time a submodel dictionary is built after connect();
                       optional afterwards (looked up from the paths list if omitted).
    """
    if submodel_path:
        ame.api.AMEChangeSubmodel(alias, submodel_name, submodel_path)
    else:
        ame.api.AMEChangeSubmodel(alias, submodel_name)
    return f"Set submodel '{submodel_name}' on '{alias}'."


# ---------- Parameters ----------

@mcp.tool()
def get_parameter_value(data_path: str) -> str:
    """Get the current value (and unit) of a parameter or state variable.

    Args:
        data_path: "param_name@alias_path", e.g. "force0@springdamper01".
    """
    value, unit = ame.api.AMEGetParameterValue(data_path)
    return json.dumps({"value": value, "unit": unit})


@mcp.tool()
def set_parameter_value(data_path: str, value: str) -> str:
    """Set the value of a parameter or the initial value of a state.

    Args:
        data_path: "param_name@alias_path", e.g. "theta@mass1port".
        value: New value (as a string, e.g. "90").
    """
    ame.api.AMESetParameterValue(data_path, value)
    return f"Set {data_path} = {value}."


@mcp.tool()
def get_parameter_infos(data_path: str) -> str:
    """Get the type, title and unit of a parameter.

    Args:
        data_path: "param_name@alias_path".
    """
    ptype, title, unit = ame.api.AMEGetParameterInfos(data_path)
    return json.dumps({"type": ptype, "title": title, "unit": unit})


# ---------- Compile & run ----------

@mcp.tool()
def generate_code() -> str:
    """Compile the active circuit. Required before running a simulation, and after any
    structural change (components, connections, submodels)."""
    ame.api.AMEGenerateCode()
    return "Code generated (compiled)."


@mcp.tool()
def set_run_parameter(name: str, value: str) -> str:
    """Set a run/simulation parameter of the active circuit.

    Args:
        name: Run parameter name. Common ones: "start_time_s", "stop_time_s", "interval_s"
              (floats, as strings), "integ_method" ("0" standard / "1" fixed step),
              "tolerance" (float string, standard integrator only), "simulation_mode"
              ("1" stabilizing / "2" dynamic / "3" both). For the full list, use
              execute_python("help(ame_apy.AMESetRunParameter)").
        value: New value as a string, e.g. "0.1".
    """
    ame.api.AMESetRunParameter(name, value)
    return f"Set run parameter {name} = {value}."


@mcp.tool()
def run_simulation() -> str:
    """Run a (temporal) simulation of the active circuit. Compile with generate_code() first,
    and again after any structural change, to make sure the run uses up-to-date code."""
    ame.api.AMERunSimulation()
    return "Simulation run complete."


# ---------- Results ----------

@mcp.tool()
def get_variable_values(data_path: str) -> str:
    """Get the time-series values of a saved variable from the last simulation run.
    Returns a JSON array of [time, value] pairs.

    Args:
        data_path: "var_name@alias_path", e.g. "x1@mass_friction1port".
    """
    values = ame.api.AMEGetVariableValues(data_path)
    return json.dumps(values)


@mcp.tool()
def get_variable_infos(data_path: str) -> str:
    """Get metadata (type, title, unit) about a variable.

    Args:
        data_path: "var_name@alias_path".
    """
    infos = ame.api.AMEGetVariableInfos(data_path)
    return json.dumps(infos)


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
