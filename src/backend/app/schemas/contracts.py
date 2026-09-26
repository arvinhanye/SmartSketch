"""Load the checked-in, generated v1 Python models from the contract source tree.

The generated module is not part of the backend setuptools package yet. Keep one loader
here so API modules consume its classes without defining parallel wire DTOs.
"""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys


_PATH = Path(__file__).resolve().parents[3] / "contracts/v1/generated/python/models.py"
_NAME = "smartsketch_contracts_v1_generated"
_spec = spec_from_file_location(_NAME, _PATH)
if _spec is None or _spec.loader is None:
    raise RuntimeError(f"Generated API models are unavailable: {_PATH}")
_module = module_from_spec(_spec)
sys.modules[_NAME] = _module
_spec.loader.exec_module(_module)

Course = _module.Course
CourseCreate = _module.CourseCreate
CourseStatus = _module.CourseStatus
Role = _module.Role
# F07 graph reads.
Chapter = _module.Chapter
GraphExchange = _module.GraphExchange
GraphStats = _module.GraphStats
KnowledgePoint = _module.KnowledgePoint
KnowledgePointDetail = _module.KnowledgePointDetail
# F08 teacher knowledge-point writes.
KnowledgePointCreate = _module.KnowledgePointCreate
KnowledgePointStatus = _module.KnowledgePointStatus
KnowledgePointUnlock = _module.KnowledgePointUnlock
KnowledgePointRef = _module.KnowledgePointRef
KnowledgePointType = _module.KnowledgePointType
Relation = _module.Relation
RelationType = _module.RelationType
SourceRef = _module.SourceRef
