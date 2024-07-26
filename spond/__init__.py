import sys
from typing import Any, Dict

if sys.version_info < (3, 10):
    from typing_extensions import TypeAlias
else:
    from typing import TypeAlias


DictFromJSON: TypeAlias = Dict[str, Any]
"""Simple type alias to annotate data retrieved from the API."""
