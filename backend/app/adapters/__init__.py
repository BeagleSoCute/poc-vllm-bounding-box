"""ทะเบียนโมเดล ลำดับในรายการนี้คือลำดับในเมนูของหน้าจอ"""
from .base import Adapter, NotConnected
from .dots_mocr import DotsMocrAdapter
from .gemini import GeminiAdapter
from .mineru import MinerUAdapter
from .paddleocr_vl import PaddleOCRVLAdapter


def _build() -> dict:
    adapters = [
        GeminiAdapter(),
        MinerUAdapter(),
        PaddleOCRVLAdapter(),
        DotsMocrAdapter(),
    ]
    return {a.id: a for a in adapters}


REGISTRY = _build()


def describe() -> list:
    out = []
    for a in REGISTRY.values():
        ok, reason = a.availability()
        out.append({"id": a.id, "name": a.name, "kind": a.kind,
                    "version": a.version(), "available": ok, "reason": reason,
                    "raw_note": a.raw_note})
    return out
