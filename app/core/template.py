"""Command template renderer with parameter substitution."""

import re
import shlex
from collections.abc import Mapping, Sequence

from app.application.dto.command_management import CommandParameterDTO
from app.core.exceptions import TemplateRenderError
from app.core.types import JsonValue

PLACEHOLDER_RE = re.compile(r"\{(\w+)\}")


def render_command(
    template: str,
    parameters: Sequence[CommandParameterDTO],
    params: Mapping[str, JsonValue],
) -> str:
    """Render a command template by substituting {placeholder} values.

    Args:
        template: Command string with {placeholder} markers.
        parameters: List of parameter definitions from CommandModel.
        params: User-provided parameter values.

    Returns:
        Rendered command string.

    Raises:
        TemplateRenderError: If placeholders are undeclared, required params are
            missing, or a value cannot be converted to string.
    """
    declared = {parameter.name for parameter in parameters}
    found = set(PLACEHOLDER_RE.findall(template))

    undeclared = found - declared
    if undeclared:
        raise TemplateRenderError(
            f"Undeclared placeholders in command: {', '.join(sorted(undeclared))}"
        )

    defaults = {parameter.name: parameter.default for parameter in parameters}

    missing = []
    for parameter in parameters:
        name = parameter.name
        is_required = parameter.required
        has_default = defaults.get(name) is not None
        if name in found and name not in params and not has_default and is_required:
            missing.append(name)
    if missing:
        raise TemplateRenderError(
            f"Missing required parameters: {', '.join(sorted(missing))}"
        )

    def _replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name in params:
            return shlex.quote(str(params[name]))
        if defaults.get(name) is not None:
            return shlex.quote(str(defaults[name]))
        return match.group(0)

    return PLACEHOLDER_RE.sub(_replace, template)
