import sys
from typing import Any, Dict

if sys.version_info < (3, 10):
    from typing_extensions import TypeAlias
else:
    from typing import TypeAlias


JSONDict: TypeAlias = Dict[str, Any]
"""Simple alias for type hinting `dict`s that can be passed to/from JSON-handling functions."""
