try:
    from ._version import version as __version__
except ImportError:
    __version__ = "unknown"

from ._sample_data import make_sample_data
from ._temporal_plots import TemporalStatistics
from ._widget import plugin_wrapper_btrack

__all__ = (
    "make_sample_data",
    "plugin_wrapper_btrack",
    "TemporalStatistics",
)
