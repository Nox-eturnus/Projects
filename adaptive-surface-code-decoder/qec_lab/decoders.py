from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np
import pymatching
import stim

from beliefmatching import (
    detector_error_model_to_check_matrices,
)
from ldpc import (
    BpOsdDecoder,
    UnionFindDecoder,
)


class DecoderAdapter(ABC):
    name: str

    @abstractmethod
    def decode(
        self,
        dets: np.ndarray,
    ) -> np.ndarray:
        raise NotImplementedError

    def decode_batch(
        self,
        dets: np.ndarray,
    ) -> np.ndarray:
        return np.vstack(
            [
                self.decode(row)
                for row in dets
            ]
        ).astype(np.uint8)


class MWPMDecoder(DecoderAdapter):
    name = "mwpm"

    def __init__(
        self,
        dem: stim.DetectorErrorModel,
    ):
        self.matching = (
            pymatching.Matching
            .from_detector_error_model(
                dem
            )
        )

    def decode(
        self,
        dets: np.ndarray,
    ) -> np.ndarray:
        return np.asarray(
            self.matching.decode(dets),
            dtype=np.uint8,
        )

    def decode_batch(
        self,
        dets: np.ndarray,
    ) -> np.ndarray:
        return np.asarray(
            self.matching.decode_batch(dets),
            dtype=np.uint8,
        )


class CorrelatedMWPMDecoder(
    DecoderAdapter
):
    name = "mwpm_correlated"

    def __init__(
        self,
        dem: stim.DetectorErrorModel,
    ):
        self.matching = (
            pymatching.Matching
            .from_detector_error_model(
                dem,
                enable_correlations=True,
            )
        )

    def decode(
        self,
        dets: np.ndarray,
    ) -> np.ndarray:
        return np.asarray(
            self.matching.decode(
                dets,
                enable_correlations=True,
            ),
            dtype=np.uint8,
        )

    def decode_batch(
        self,
        dets: np.ndarray,
    ) -> np.ndarray:
        return np.asarray(
            self.matching.decode_batch(
                dets,
                enable_correlations=True,
            ),
            dtype=np.uint8,
        )


class BPOSDDecoder(DecoderAdapter):
    name = "bp_osd"

    def __init__(
        self,
        dem: stim.DetectorErrorModel,
        max_iter: int = 10,
        osd_method: str = "OSD_0",
        osd_order: int = 0,
    ):
        matrices = (
            detector_error_model_to_check_matrices(
                dem
            )
        )

        self.observables_matrix = (
            matrices.observables_matrix
        )

        self.decoder = BpOsdDecoder(
            matrices.check_matrix,
            error_channel=list(
                matrices.priors
            ),
            max_iter=max_iter,
            bp_method="minimum_sum",
            schedule="parallel",
            osd_method=osd_method,
            osd_order=osd_order,
        )

    def decode(
        self,
        dets: np.ndarray,
    ) -> np.ndarray:
        estimated_error = (
            self.decoder.decode(
                np.asarray(
                    dets,
                    dtype=np.uint8,
                )
            )
        )

        logical_prediction = (
            self.observables_matrix
            @ estimated_error
        ) % 2

        return np.asarray(
            logical_prediction,
            dtype=np.uint8,
        ).reshape(-1)


class UnionFindSurfaceDecoder(
    DecoderAdapter
):
    name = "union_find"

    def __init__(
        self,
        dem: stim.DetectorErrorModel,
    ):
        matrices = (
            detector_error_model_to_check_matrices(
                dem
            )
        )

        self.observables_matrix = (
            matrices.observables_matrix
        )

        self.decoder = UnionFindDecoder(
            matrices.check_matrix,
            uf_method="inversion",
        )

    def decode(
        self,
        dets: np.ndarray,
    ) -> np.ndarray:
        estimated_error = (
            self.decoder.decode(
                np.asarray(
                    dets,
                    dtype=np.uint8,
                )
            )
        )

        logical_prediction = (
            self.observables_matrix
            @ estimated_error
        ) % 2

        return np.asarray(
            logical_prediction,
            dtype=np.uint8,
        ).reshape(-1)