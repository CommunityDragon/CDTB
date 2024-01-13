import logging
logger = logging.getLogger(__name__)

from cdtb.storage import (
    Storage,
    Patch,
    PatchElement,
)
from cdtb.wad import (
    Wad,
)
from cdtb.export import (
    Exporter,
    CdragonRawPatchExporter,
)

# import storages to register them
import cdtb.rads
import cdtb.patcher

