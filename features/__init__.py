"""Sliding-window feature pipeline for NeuroLens Model A."""

from .extractor import FEATURE_KEYS_FOR_ZSCORE, FeatureRuntimeContext, compute_window_features
from .personalization import RollingBaseline
from .pipeline import RealTimeFeaturePipeline
from .windowing import EventWindow, iter_sliding_windows

__all__ = [
    "EventWindow",
    "FEATURE_KEYS_FOR_ZSCORE",
    "FeatureRuntimeContext",
    "RollingBaseline",
    "RealTimeFeaturePipeline",
    "compute_window_features",
    "iter_sliding_windows",
]
