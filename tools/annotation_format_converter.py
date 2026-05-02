"""Compatibility entrypoints for annotation conversion."""

from __future__ import annotations

from tools.annotation_converters.base import AnnotationConversionReport
from tools.annotation_converters.annotation_merge import (
    convert_annotation_merge_file,
    merge_annotation_payloads as merge_current_annotation_payloads,
)
from tools.annotation_converters.legacy_coordinate_convert import (
    convert_annotation_file,
    convert_manual_old_big_map_annotation_payload,
    convert_old_big_map_annotation_payload,
    merge_annotation_payloads,
)

__all__ = [
    "AnnotationConversionReport",
    "convert_annotation_merge_file",
    "convert_annotation_file",
    "convert_manual_old_big_map_annotation_payload",
    "convert_old_big_map_annotation_payload",
    "merge_current_annotation_payloads",
    "merge_annotation_payloads",
]
