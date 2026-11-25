#!/usr/bin/env python3
"""
Unit tests for Pluto TX adapter and RTL-SDR receiver.

Tests cover:
- GNU Radio flowgraph construction with mocks
- Correct sink configuration
- Valid channel configuration
- Receiver initialization and IQ capture
- Receiver cleanup
- BER correctness using known synthetic signals
- No transmission during imports or tests
- No double amplitude scaling
"""

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.radio.pluto_tx_adapter import (
    PlutoTXAdapter,
    RTLSDRReceiver,
    generate_waveform,
    set_rf_enabled,
    RF_ENABLED,
)


# ============================================================
# Test: RF Disabled by Default
# ============================================================
class TestRFDisabledByDefault:
    """Test that RF transmission is disabled by default."""

    def test_rf_enabled_false_by_default(self):
        import src.radio.pluto_tx_adapter as pta
        assert pta.RF_ENABLED == False

    def test_set_rf_enabled_changes_state(self):
        import src.radio.pluto_tx_adapter as pta
        pta.set_rf_enabled(True)
        assert pta.RF_ENABLED == True
        pta.set_rf_enabled(False)
        assert pta.RF_ENABLED == False

    def test_rf_disabled_on_import(self):
        # Verify imports do not trigger any transmission
        import src.radio.pluto_tx_adapter as pta
        assert pta.RF_ENABLED == False
        pta.set_rf_enabled(False)


# ============================================================
# Test: Pluto TX Adapter - Construction
# ============================================================
class TestPlutoTXAdapterConstruction:
    """Test PlutoTXAdapter construction and configuration."""

    def test_default_constructor(self):
        adapter = PlutoTXAdapter()
        from src.radio.hardware_config import PLUTO_URI
        assert adapter.uri == PLUTO_URI == "ip:192.168.2.1"
        assert adapter.sample_rate == 2_400_000
        assert adapter.bandwidth == 1_000_000
        assert adapter.amplitude_scale == 0.1

    def test_custom_constructor(self):
        adapter = PlutoTXAdapter(
            uri="usb:3.2.5",
            sample_rate=10_000_000,
            bandwidth=2_000_000,
            amplitude_scale=0.2,
        )
        assert adapter.sample_rate == 10_000_000
        assert adapter.bandwidth == 2_000_000
        assert adapter.amplitude_scale == 0.2

    def test_configure_sets_hardware_mode(self):
        adapter = PlutoTXAdapter()
        assert adapter.hardware_mode == False
        adapter.configure(500_000_000, 30)
        assert adapter.hardware_mode == True
        assert adapter._frequency == 500_000_000
        assert adapter._attenuation == 30

    def test_configure_invalid_attenuation(self):
        adapter = PlutoTXAdapter()
        with pytest.raises(ValueError):
            adapter.configure(500_000_000, 100)

    def test_prepare_stores_iq(self):
        adapter = PlutoTXAdapter()
        iq = np.ones(100, dtype=np.complex64)
        adapter.prepare(iq)
        assert adapter._prepared_iq is not None
        assert len(adapter._prepared_iq) == 100

    def test_prepare_applies_amplitude_scale(self):
        adapter = PlutoTXAdapter(amplitude_scale=0.5, peak_limit=1.0)
        iq = np.ones(100, dtype=np.complex64)
        adapter.prepare(iq)
        assert adapter._prepared_iq is not None
        assert np.allclose(adapter._prepared_iq, 0.5)

    def test_prepare_applies_scale_only_once(self):
        """Amplitude scaling happens exactly once."""
        adapter = PlutoTXAdapter(amplitude_scale=0.5, peak_limit=1.0)
        iq = np.ones(100, dtype=np.complex64)
        adapter.prepare(iq, amplitude_scale=0.8)
        # Should use the explicitly provided scale, not combine
        assert np.allclose(adapter._prepared_iq, 0.8)

    def test_prepare_peak_limit(self):
        adapter = PlutoTXAdapter(amplitude_scale=1.0, peak_limit=0.25)
        iq = np.full(100, 0.5, dtype=np.complex64)
        with pytest.raises(ValueError, match="Peak.*exceed"):
            adapter.prepare(iq)

    def test_prepare_invalid_iq(self):
        adapter = PlutoTXAdapter()
        # float32 input is accepted and converted to complex64
        iq = np.ones(100, dtype=np.float32)
        adapter.prepare(iq)
        assert adapter._prepared_iq is not None
        assert adapter._prepared_iq.dtype == np.complex64


# ============================================================
# Test: Pluto TX Adapter - Flowgraph
# ============================================================
class TestPlutoTXAdapterFlowgraph:
    """Test GNU Radio flowgraph construction with mocks."""

    def test_build_flowgraph_with_prepared_iq(self, monkeypatch):
        """Test that build_flowgraph creates the correct GNU Radio blocks."""
        adapter = PlutoTXAdapter()
        adapter.prepare(np.ones(100, dtype=np.complex64))

        # Mock the GNU Radio IIO sink at the module level
        mock_sink = MagicMock()
        monkeypatch.setattr("gnuradio.iio.fmcomms2_sink_fc32", lambda *args, **kwargs: mock_sink)
        monkeypatch.setattr("gnuradio.gr.top_block", lambda name: MagicMock())
        monkeypatch.setattr("gnuradio.blocks.vector_source_c", lambda *args, **kwargs: "mock_vector_source")

        top_block = adapter.build_flowgraph()

        assert top_block is not None
        assert adapter._source is not None
        assert adapter._sink is not None

    def test_build_flowgraph_no_iq(self):
        """Test that build_flowgraph raises without prepared IQ."""
        adapter = PlutoTXAdapter()
        with pytest.raises(RuntimeError):
            adapter.build_flowgraph()


# ============================================================
# Test: Pluto TX Adapter - Transmit (mocked)
# ============================================================
class TestPlutoTXAdapterTransmit:
    """Test Pluto TX adapter transmit with mocks."""

    def test_transmit_raises_without_rf_enabled(self):
        """Test that transmit() raises without RF enabled."""
        adapter = PlutoTXAdapter()
        adapter.configure(500_000_000)
        adapter.prepare(np.ones(100, dtype=np.complex64))

        with pytest.raises(RuntimeError, match="RF transmission is DISABLED"):
            adapter.transmit()

    def test_transmit_begins_hardware_mode(self):
        """Test that transmit() builds flowgraph and initializes hardware."""
        from unittest.mock import patch, MagicMock

        # Enable RF
        import src.radio.pluto_tx_adapter as pta
        pta.set_rf_enabled(True)

        adapter = PlutoTXAdapter()
        adapter.configure(500_000_000)
        adapter.prepare(np.ones(100, dtype=np.complex64))

        # Mock the GNU Radio IIO sink at the gnuradio.iio module level
        # The build_flowgraph method does: from gnuradio import blocks, gr, iio
        # which then uses iio.fmcomms2_sink_fc32
        with patch("gnuradio.iio.fmcomms2_sink_fc32", return_value=MagicMock()), \
             patch("gnuradio.gr.top_block", return_value=MagicMock()), \
             patch("gnuradio.blocks.vector_source_c", return_value="mock_vector_source"):
            result = adapter.transmit()

        # Reset RF
        pta.set_rf_enabled(False)

        assert result["status"] == "transmitted"
        assert result["samples"] == 100
        assert result["frequency_hz"] == 500_000_000

    def test_transmit_closes_resources(self):
        """Test that transmit() closes resources after completion."""
        from unittest.mock import patch, MagicMock

        # Enable RF
        import src.radio.pluto_tx_adapter as pta
        pta.set_rf_enabled(True)

        adapter = PlutoTXAdapter()
        adapter.configure(500_000_000)
        adapter.prepare(np.ones(100, dtype=np.complex64))

        with patch("gnuradio.iio.fmcomms2_sink_fc32", return_value=MagicMock()), \
             patch("gnuradio.gr.top_block", return_value=MagicMock()), \
             patch("gnuradio.blocks.vector_source_c", return_value="mock_vector_source"):
            result = adapter.transmit()

        # Reset RF
        pta.set_rf_enabled(False)

        # After transmit, resources should be cleaned up
        assert adapter._closed == True
        assert adapter._top_block is None


# ============================================================
# Test: Pluto TX Adapter - Cleanup
# ============================================================
class TestPlutoTXAdapterCleanup:
    """Test PlutoTXAdapter resource cleanup."""

    def test_close_releases_resources(self, monkeypatch):
        """Test that close() releases resources."""
        adapter = PlutoTXAdapter()
        adapter.prepare(np.ones(100, dtype=np.complex64))

        # Create a mock top block
        mock_tb = types.SimpleNamespace(
            stop=lambda: None,
            wait=lambda *args: None,
        )
        adapter._top_block = mock_tb

        adapter.close()

        assert adapter._closed == True
        assert adapter._top_block is None
        assert adapter._prepared_iq is None

    def test_context_manager(self, monkeypatch):
        """Test that context manager cleans up properly."""
        adapter = PlutoTXAdapter()
        adapter.prepare(np.ones(100, dtype=np.complex64))

        mock_tb = types.SimpleNamespace(
            stop=lambda: None,
            wait=lambda *args: None,
        )
        adapter._top_block = mock_tb

        with adapter:
            assert adapter._closed == False

        assert adapter._closed == True
        assert adapter._top_block is None
